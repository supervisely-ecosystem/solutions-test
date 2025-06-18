import mimetypes
import os
import smtplib
from email.message import EmailMessage
from typing import List, Literal, Optional, Union

import supervisely as sly
from supervisely.app.widgets import Button, Icons, NotificationBox, SolutionCard
from supervisely.solution.base_node import SolutionCardNode, SolutionElement

# Common email domain → (SMTP host, port)
SMTP_PROVIDERS = {
    "gmail.com": ("smtp.gmail.com", 587),
    "outlook.com": ("smtp.office365.com", 587),
    "hotmail.com": ("smtp.office365.com", 587),
    "live.com": ("smtp.office365.com", 587),
    "yahoo.com": ("smtp.mail.yahoo.com", 587),
    "icloud.com": ("smtp.mail.me.com", 587),
}


class SendEmailNode(SolutionElement):
    class EmailCredentials:
        def __init__(
            self,
            username: str,
            password: str,
            host: Optional[str] = None,
            port: Optional[int] = None,
        ):
            if (not username or not password) or (username.strip() == "" or password.strip() == ""):
                raise ValueError("Username and password must be provided.")
            self.username = username
            self.password = password

            domain = self.get_domain()
            _host, _port = SMTP_PROVIDERS.get(domain, (None, None))
            self.host = host or _host
            self.port = port or _port
            if not self.host or not self.port:
                raise ValueError(
                    f"No SMTP settings found for domain '{domain}'. "
                    "Please pass smtp_host and smtp_port explicitly."
                )

        def get_domain(self) -> str:
            """
            Extracts the email domain from the username.
            """
            return self.username.split("@")[-1].lower()

    def __init__(
        self,
        credentials: EmailCredentials,
        subject: str = "Supervisely Notification",
        body: str = "",
        target_addresses: Union[str, List[str]] = None,
        title: str = "Send Email",
        description: str = "Send an email notification.",
        width: int = 250,
        x: int = 0,
        y: int = 0,
        icon: Optional[Icons] = None,
        tooltip_position: Literal["left", "right"] = "right",
        *args,
        **kwargs,
    ):
        self.creds = credentials
        self.title = title
        self.description = description
        self.width = width
        self.icon = icon or self._get_default_icon()

        self.tooltip_position = tooltip_position

        self._send_btn = Button(
            "Send",
            icon="zmdi zmdi-play",
            button_size="mini",
            plain=True,
            button_type="text",
        )

        @self._send_btn.click
        def send_click_cb():
            self.hide_finished_badge()
            self.hide_failed_badge()
            self.send_email()

        self.subject = subject
        self._body = body
        self.to_addrs = target_addresses or self.creds.username  # Default to sender's email

        self.error_nofitication = NotificationBox(
            "Authentication Error",
            "Failed to authenticate with the provided email credentials. "
            "Please check your username and password.",
            box_type="error",
        )
        self.error_nofitication.hide()

        self.card = self._create_card()
        self.node = SolutionCardNode(content=self.card, x=x, y=y)
        super().__init__(*args, **kwargs)

    @property
    def body(self) -> str:
        """
        Returns the body of the email.
        """
        return self._body

    @body.setter
    def body(self, value: str) -> None:
        """
        Sets the body of the email.
        """
        if not isinstance(value, str):
            raise ValueError("Email body must be a string.")
        self._body = value

    def _get_default_icon(self) -> Icons:
        """
        Returns a default icon for the SendEmailNode.
        """
        color, bg_color = self._random_pretty_color()
        return Icons(class_name="zmdi zmdi-email", color=color, bg_color=bg_color)

    def _random_pretty_color(self) -> str:
        import colorsys
        import random

        icon_color_hsv = (random.random(), random.uniform(0.5, 1.0), random.uniform(0.7, 1.0))
        icon_color_rgb = colorsys.hsv_to_rgb(*icon_color_hsv)
        icon_color_hex = "#{:02X}{:02X}{:02X}".format(*[int(c * 255) for c in icon_color_rgb])

        bg_color_hsv = (
            icon_color_hsv[0],
            icon_color_hsv[1] * 0.3,
            min(icon_color_hsv[2] + 0.3, 1.0),
        )
        bg_color_rgb = colorsys.hsv_to_rgb(*bg_color_hsv)
        bg_color_hex = "#{:02X}{:02X}{:02X}".format(*[int(c * 255) for c in bg_color_rgb])

        return icon_color_hex, bg_color_hex

    def _create_card(self) -> SolutionCard:
        """
        Creates and returns the SolutionCard for the SendEmailNode.
        """
        return SolutionCard(
            title=self.title,
            tooltip=self._create_tooltip(),
            content=[self.error_nofitication],
            width=self.width,
            tooltip_position=self.tooltip_position,
            icon=self.icon,
        )

    def _create_tooltip(self) -> SolutionCard.Tooltip:
        """
        Creates and returns the tooltip for the SendEmailNode.
        """
        return SolutionCard.Tooltip(
            description=self.description,
            content=[self._send_btn],
        )

    def send_email(
        self,
        from_addr: Optional[str] = None,
        attachments: Optional[List[str]] = None,
    ) -> None:
        """
        Send an email via SMTP. If smtp_host/port are not provided,
        they will be inferred from the username's email domain using SMTP_PROVIDERS.
        """

        msg = EmailMessage()
        msg["Subject"] = self.subject
        msg["From"] = from_addr or self.creds.username
        msg["To"] = ", ".join(self.to_addrs) if isinstance(self.to_addrs, list) else self.to_addrs
        msg.set_content(self.body)

        for path in attachments or []:
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Attachment not found: {path}")
            ctype, encoding = mimetypes.guess_type(path)
            maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
            with open(path, "rb") as fp:
                msg.add_attachment(
                    fp.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(path)
                )

        with smtplib.SMTP(self.creds.host, self.creds.port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            try:
                server.login(self.creds.username, self.creds.password)
            except smtplib.SMTPAuthenticationError:
                sly.logger.error("Failed to authenticate with the provided email credentials.")
                self.show_failed_badge()
                return
            except (smtplib.SMTPException, smtplib.SMTPServerDisconnected) as e:
                sly.logger.error(f"Failed to send email: {e}", exc_info=False)
                self.set_error_notification(
                    title="Email Sending Error",
                    msg=f"Failed to send email: {e}",
                )
                self.show_failed_badge()
                return
            server.send_message(msg)
            self.show_finished_badge()
            sly.logger.info(f"Email sent to {self.to_addrs}")

    def show_finished_badge(self):
        """
        Updates the card to show that the evaluation is finished.
        """
        self.card.update_badge_by_key(key="Finished", label="✅", plain=True, badge_type="success")

    def hide_finished_badge(self):
        """
        Hides the finished badge from the card.
        """
        self.card.remove_badge_by_key(key="Finished")

    def show_running_badge(self):
        """
        Updates the card to show that the evaluation is running.
        """
        self.card.update_badge_by_key(key="Sending", label="⚡", plain=True, badge_type="warning")

    def hide_running_badge(self):
        """
        Hides the running badge from the card.
        """
        self.card.remove_badge_by_key(key="Sending")

    def show_failed_badge(self):
        """
        Updates the card to show that the evaluation has failed.
        """
        self.card.update_badge_by_key(key="Failed", label="❌", plain=True, badge_type="error")
        self.error_nofitication.show()

    def hide_failed_badge(self):
        """
        Hides the failed badge from the card.
        """
        self.card.remove_badge_by_key(key="Failed")
        self.error_nofitication.hide()

    def set_error_notification(self, title, msg):
        self.error_nofitication.title = title
        self.error_nofitication.description = msg
