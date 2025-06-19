import mimetypes
import os
import smtplib
from email.message import EmailMessage
from typing import List, Literal, Optional, Union

import supervisely as sly
from apscheduler.triggers.cron import CronTrigger
from supervisely.app.widgets import (
    Button,
    CheckboxField,
    Container,
    Field,
    Icons,
    Input,
    InputNumber,
    NotificationBox,
    SolutionCard,
    Switch,
    TextArea,
    TimePicker,
)
from supervisely.app.widgets.dialog.dialog import Dialog
from supervisely.solution.base_node import SolutionCardNode, SolutionElement
from supervisely.solution.scheduler import TasksScheduler

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

        self.task_scheduler = TasksScheduler()

        # self._send_btn = Button(
        #     "Send",
        #     icon="zmdi zmdi-play",
        #     button_size="mini",
        #     plain=True,
        #     button_type="text",
        # )

        # @ todo change to appropriate icons
        self._settings_btn = Button(
            "Notifications Settings",
            icon="zmdi zmdi-settings",
            plain=True,
            button_type="text",
            button_size="mini",
        )
        self._history_btn = Button(
            "Notification History",
            icon="zmdi zmdi-format-subject",
            plain=True,
            button_type="text",
            button_size="mini",
        )

        # @self._send_btn.click
        # def send_click_cb():
        #     self.hide_finished_badge()
        #     self.hide_failed_badge()
        #     self.send_email()

        self._run_after_comparison = False

        self.subject = subject
        self._body = body
        self.to_addrs = target_addresses or self.creds.username  # Default to sender's email
        self._modal_settings = {}

        # self.error_nofitication = NotificationBox(
        #     "Authentication Error",
        #     "Failed to authenticate with the provided email credentials. "
        #     "Please check your username and password.",
        #     box_type="error",
        # )
        # self.error_nofitication.hide()
        self.settings_modal = self._init_settings_modal()
        self.history_modal = self._init_history_modal()

        @self._settings_btn.click
        def settings_click_cb():
            self.settings_modal.show()

        self._history_btn.disable()

        @self._history_btn.click
        def history_click_cb():
            self.history_modal.show()

        self.card = self._create_card()
        self.node = SolutionCardNode(content=self.card, x=x, y=y)
        self.modals = [self.settings_modal, self.history_modal]
        super().__init__(*args, **kwargs)

    @property
    def run_after_comparison(self) -> bool:
        """
        Returns whether the email should be sent after each comparison.
        """
        return self._run_after_comparison

    @run_after_comparison.setter
    def run_after_comparison(self, value: bool) -> None:
        """
        Sets whether the email should be sent after each comparison.
        """
        if not isinstance(value, bool):
            raise ValueError("run_after_comparison must be a boolean value.")
        self._run_after_comparison = value

    def _init_history_modal(self):
        history_modal = Dialog(
            title="Notification History",
            content=Container(
                [
                    Field(
                        "History",
                        "This feature is not implemented yet.",
                    ),
                ]
            ),
            size="tiny",
        )
        return history_modal

    def _init_settings_modal(self):
        """
        Initializes the settings modal for the SendEmailNode.
        """
        # from supervisely.app.widgets import ElementTagsList

        subject_input = Input(
            "", 0, 300, placeholder="Enter email subject here...", type="textarea"
        )
        subject_input_field = Field(
            subject_input, "Email Subject", "Configure the subject of the email notification."
        )

        body_input = TextArea(
            placeholder="Enter email body here...",
            rows=20,
        )
        body_input_field = Field(
            body_input,
            "Email Body",
            "Configure the body of the email notification. Leave empty to use default.",
        )
        # @todo: separate widget
        to_addrs_input = Input(
            "",
            0,
            300,
            placeholder="Enter recipient email addresses (comma-separated)...",
            type="textarea",
        )
        to_addrs_input_field = Field(
            to_addrs_input,
            "Recipient Addresses",
            "Configure the recipient email addresses. "
            "You can specify multiple addresses separated by commas.",
        )

        run_daily_switch = Switch(False)
        run_daily_time_picker = TimePicker("09:00")
        run_daily_time_picker.disable()

        @run_daily_switch.value_changed
        def run_daily_switch_change_cb(is_on: bool):
            if is_on:
                run_daily_time_picker.enable()
            else:
                run_daily_time_picker.disable()

        run_daily_field = Field(
            Container([run_daily_switch, run_daily_time_picker]),
            "Run Daily",
            "Enable this to send email notifications daily at the specified time.",
        )

        run_after_comparison_switch = Switch(True)
        run_after_comparison_switch_field = Field(
            run_after_comparison_switch,
            "Run After Comparison",
            "Enable this to send email notifications after each comparison.",
        )
        apply_btn = Button(
            "Apply",
        )

        def get_modal_settings():
            """
            Returns the current settings from the modal.
            """
            return {
                "subject": subject_input.get_value() or None,
                "body": body_input.get_value().strip() or None,
                "to_addrs": [
                    addr.strip() for addr in to_addrs_input.get_value().split(",") if addr.strip()
                ]
                or None,
                "run_daily": run_daily_switch.is_on(),
                "run_daily_time": run_daily_time_picker.get_value(),
                "run_after_comparison": run_after_comparison_switch.is_on(),
            }

        @apply_btn.click
        def modal_save_settings():
            self._modal_settings = get_modal_settings()
            self.run_after_comparison = self._modal_settings.get("run_after_comparison", False)
            run_daily = self._modal_settings.get("run_daily", False)
            if run_daily or self.run_after_comparison:
                self.show_automated_badge()
            else:
                self.hide_automated_badge()

            self.subject = self._modal_settings.get("subject", "Supervisely Notification")
            self.body = self._modal_settings.get("body", "")
            self.to_addrs = self._modal_settings.get("to_addrs", self.creds.username)
            self._update_properties()
            self.update_scheduler()
            self.settings_modal.hide()

        modal_layout = Container(
            [
                subject_input_field,
                body_input_field,
                to_addrs_input_field,
                run_daily_field,
                run_after_comparison_switch_field,
                apply_btn,
            ]
        )
        settings_modal = Dialog("Notification Settings", content=modal_layout, size="tiny")
        return settings_modal

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

        icon_color_hsv = (random.random(), random.uniform(0.6, 0.9), random.uniform(0.4, 0.7))
        icon_color_rgb = colorsys.hsv_to_rgb(*icon_color_hsv)
        icon_color_hex = "#{:02X}{:02X}{:02X}".format(*[int(c * 255) for c in icon_color_rgb])

        bg_color_hsv = (
            icon_color_hsv[0],
            icon_color_hsv[1] * 0.3,
            min(icon_color_hsv[2] + 0.4, 1.0),
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
            # content=[self.error_nofitication],
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
            content=[self._settings_btn, self._history_btn],
            properties=[
                {
                    "key": "Send",
                    "value": "after comparison",
                    "link": False,
                    "highlight": True,
                },
                {
                    "key": "Total",
                    "value": "0 notifications",
                    "link": False,
                    "highlight": False,
                },
                {
                    "key": "Email",
                    "value": f"{self.creds.username}",
                    "link": True,
                    "highlight": False,
                },
            ],
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
        self.hide_finished_badge()
        self.hide_failed_badge()
        self.show_running_badge()

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
                self.hide_running_badge()
                self.show_failed_badge()
                return
            except (smtplib.SMTPException, smtplib.SMTPServerDisconnected) as e:
                sly.logger.error(f"Failed to send email: {e}", exc_info=False)
                # self.set_error_notification(
                #     title="Email Sending Error",
                #     msg=f"Failed to send email: {e}",
                # )
                self.hide_running_badge()
                self.show_failed_badge()
                return
            server.send_message(msg)
            self.hide_running_badge()
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
        # self.error_nofitication.show()

    def hide_failed_badge(self):
        """
        Hides the failed badge from the card.
        """
        self.card.remove_badge_by_key(key="Failed")
        # self.error_nofitication.hide()

    def show_automated_badge(self):
        """
        Updates the card to show that the comparison is automated.
        """
        self.card.update_badge_by_key(key="Automated", label="🤖", plain=True, badge_type="success")

    def hide_automated_badge(self):
        """
        Hides the automated badge from the card.
        """
        self.card.remove_badge_by_key(key="Automated")

    # def set_error_notification(self, title, msg):
    #     self.error_nofitication.title = title
    #     self.error_nofitication.description = msg

    def _update_properties(self):
        m = self._modal_settings
        use_daily = m.get("run_daily", False)
        use_after_comparison = m.get("run_after_comparison", True)
        send_value = None
        if use_daily and use_after_comparison:
            send_value = "every day / after comparison"
        elif use_daily:
            send_value = "every day"
        elif use_after_comparison:
            send_value = "after comparison"
        else:
            send_value = "never"
        new_propetries = [
            {
                "key": "Send",
                "value": send_value,
                "link": False,
                "highlight": True,
            },
            {
                "key": "Total",
                "value": "0 notifications",
                "link": False,
                "highlight": False,
            },
            {
                "key": "Email",
                "value": f"{self.creds.username}",
                "link": True,
                "highlight": False,
            },
        ]
        for prop in new_propetries:
            self.card.update_property(**prop)

    def update_scheduler(self):
        if not self._modal_settings:
            return

        m = self._modal_settings
        use_daily = m.get("run_daily", False)
        if not use_daily:
            self.task_scheduler.remove_task("send_email_daily")

        time = m.get("run_daily_time", "09:00")
        hour, minute = map(int, time.split(":"))
        tigger = CronTrigger(hour=hour, minute=minute, second=0)
        job = self.task_scheduler.scheduler.add_job(
            self.send_email,
            tigger,
            id="send_email_daily",
            replace_existing=True,
        )
        self.task_scheduler.jobs[job.id] = job
        sly.logger.info(
            f"[SCHEDULER]: Job '{job.id}' scheduled to send emails at {time} every day."
        )
