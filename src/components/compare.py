import time
from typing import Callable, Literal, Optional
from uuid import uuid4

import supervisely as sly
from supervisely.app.widgets import (
    Button,
    Container,
    Field,
    Icons,
    InputNumber,
    NotificationBox,
    SolutionCard,
    Switch,
)
from supervisely.app.widgets.dialog.dialog import Dialog
from supervisely.solution.base_node import Automation, SolutionCardNode, SolutionElement


class ComparisonAutomation(Automation):
    """
    Automation for running model comparison evaluations.
    """

    def __init__(self, func: Callable):
        super().__init__()
        self.job_id = f"compare_models_{uuid4()}"
        self.func = func

    def apply(self, sec: int, *args) -> None:
        self.scheduler.add_job(
            self.func, interval=sec, job_id=self.job_id, replace_existing=True, *args
        )
        sly.logger.info(
            f"Scheduled model comparison job with ID {self.job_id} every {sec} seconds."
        )

    def remove(self):
        if self.scheduler.is_job_scheduled(self.job_id):
            self.scheduler.remove_job(self.job_id)
            sly.logger.info(f"Removed scheduled job: {self.job_id}")
        else:
            sly.logger.warning(f"Job {self.job_id} is not scheduled, cannot remove it.")


class CompareNode(SolutionElement):

    APP_SLUG = "supervisely-ecosystem/model-benchmark"
    COMPARISON_ENDPOINT = "run_comparison"

    def __init__(
        self,
        api: sly.Api,
        project_info: sly.ProjectInfo,
        title: str,
        description: str,
        width: int = 250,
        x: int = 0,
        y: int = 0,
        icon: Optional[Icons] = None,
        tooltip_position: Literal["left", "right"] = "right",
        agent_id: Optional[int] = None,
        evaluation_dirs: Optional[list[str]] = None,
        *args,
        **kwargs,
    ):
        """A node for comparing evaluation reports of different models in Supervisely."""
        self.api = api
        self.project = project_info
        self.team_id = project_info.team_id
        self.workspace_id = project_info.workspace_id
        self.title = title
        self.description = description
        self.width = width
        self.icon = icon or self._get_default_icon()
        self.tooltip_position = tooltip_position
        self.eval_dirs = evaluation_dirs

        self.result_comparison_dir = None
        self.result_comparison_link = None
        self.result_best_checkpoint = None
        self.is_automated = False

        self.agent_id = agent_id or self.get_available_agent_id()
        if self.agent_id is None:
            raise ValueError("No available agent found. Please check your agents.")

        periodic_automation = ComparisonAutomation(self.send_comparison_request)
        automation_switch = Switch(self.is_automated)
        automation_periodic_input = InputNumber(60, min=15, max=3600)
        automation_periodic_input.disable()
        apply_btn = Button(
            "Apply settings",
            button_type="primary",
        )
        apply_btn.disable()
        interval_field = Field(
            automation_periodic_input,
            "Interval (seconds)",
            "Set the interval for periodic comparison.",
        )
        automation_modal_layout = Container(
            [
                Field(
                    automation_switch,
                    "Periodic comparison",
                    "Configure whether you want to automate the comparison process.",
                ),
                interval_field,
                apply_btn,
                Field(Container(), "Conditional comparison", "Not implemented yet."),
            ]
        )
        automation_modal = Dialog("Automation Settings", automation_modal_layout, "tiny")

        @automation_switch.value_changed
        def automation_switch_change_cb(value: bool):
            self.is_automated = value
            if value:
                automation_periodic_input.enable()
                apply_btn.enable()
            else:
                automation_periodic_input.disable()
                apply_btn.disable()
                periodic_automation.remove()
                sly.logger.info("Periodic comparison automation disabled.")
                self.hide_automated_badge()
                self._update_properties()

        @apply_btn.click
        def apply_automation():
            sec = automation_periodic_input.get_value()
            periodic_automation.apply(sec)
            sly.logger.info(f"Scheduled periodic comparison every {sec} seconds.")
            automation_modal.hide()
            self._update_properties()
            self.show_automated_badge()

        self._automate_btn = Button(
            "Automate",
            icon="zmdi zmdi-settings",
            button_size="mini",
            plain=True,
            button_type="text",
        )
        self._run_btn = Button(
            "Run manually",
            icon="zmdi zmdi-play",
            button_size="mini",
            plain=True,
            button_type="text",
        )
        self._comparison_history_btn = Button(
            "Comparison history (reports)",
            icon="zmdi zmdi-format-list-bulleted",
            button_size="mini",
            plain=True,
            button_type="text",
        )
        self._task_history_btn = Button(
            "Tasks history (logs)",
            icon="zmdi zmdi-format-list-bulleted",
            button_size="mini",
            plain=True,
            button_type="text",
        )

        @self._automate_btn.click
        def automate_click_cb():
            automation_modal.show()

        @self._run_btn.click
        def run_click_cb():
            self.send_comparison_request()

        self._comparison_history_btn.disable()

        @self._comparison_history_btn.click
        def comparison_history_click_cb():
            sly.logger.warning("Comparison history button is not implemented yet.")

        self._task_history_btn.disable()

        @self._task_history_btn.click
        def task_history_click_cb():
            sly.logger.warning("Task history button is not implemented yet.")

        self.show_warning = self.eval_dirs is None or len(self.eval_dirs) < 2
        if self.show_warning:
            self._run_btn.disable()

        self.warning = NotificationBox(
            "Not enough evaluation reports",
            "Please select at least two evaluation reports to compare.",
            box_type="warning",
        )
        if not self.show_warning:
            self.warning.hide()

        self.failed_notification = NotificationBox(
            "Evaluation Failed",
            "Failed to run the evaluation. Please check the logs for more details.",
            box_type="error",
        )
        self.failed_notification.hide()

        self.card = self._create_card()
        self.node = SolutionCardNode(content=self.card, x=x, y=y)
        self.modals = [automation_modal]

        self._finish_callbacks = []

        super().__init__(*args, **kwargs)

    @property
    def evaluation_dirs(self) -> list[str]:
        """
        Returns the list of evaluation directories.
        """
        return self.eval_dirs

    @evaluation_dirs.setter
    def evaluation_dirs(self, value: list[str]):
        """
        Sets the evaluation directories and enables the run button if directories are provided.
        """
        self.eval_dirs = value
        if value:
            self._run_btn.enable()
        else:
            self._run_btn.disable()

        self.show_warning = self.eval_dirs is None or len(self.eval_dirs) < 2
        self.warning.show() if self.show_warning else self.warning.hide()

    def _create_card(self) -> SolutionCard:
        """
        Creates and returns the SolutionCard for the Compare widget.
        """
        content = [self.warning, self.failed_notification]
        return SolutionCard(
            title=self.title,
            tooltip=self._create_tooltip(),
            # content=content,
            width=self.width,
            icon=self.icon,
            tooltip_position=self.tooltip_position,
        )

    def _create_tooltip(self) -> SolutionCard.Tooltip:
        content = [
            self._automate_btn,
            self._run_btn,
            self._comparison_history_btn,
            self._task_history_btn,
        ]
        properties = [
            {
                "key": "Best model",
                "value": "Unknown",
                "highlight": True,
                "link": False,
            },
            {"key": "Automatic re-deployment", "value": "✖", "highlight": False, "link": False},
        ]
        return SolutionCard.Tooltip(
            description=self.description, content=content, properties=properties
        )

    def run_evaluator_session_if_needed(self):
        module_id = self.api.app.get_ecosystem_module_id(self.APP_SLUG)
        available_sessions = self.api.app.get_sessions(
            self.team_id, module_id, statuses=[self.api.task.Status.STARTED]
        )
        session_running = len(available_sessions) > 0
        if session_running:
            sly.logger.info("Model Benchmark Evaluator session is already running, skipping start.")
            return available_sessions[0].task_id

        sly.logger.info("Starting Model Benchmark Evaluator task...")
        task_info_json = self.api.task.start(
            agent_id=self.agent_id,
            app_id=None,
            workspace_id=self.workspace_id,
            description=f"Solutions: {self.api.task_id}",
            module_id=module_id,
        )
        if task_info_json is None:
            raise RuntimeError("Failed to start the evaluation task.")
        task_id = task_info_json["taskId"]

        current_time = time.time()
        while task_status := self.api.task.get_status(task_id) != self.api.task.Status.STARTED:
            sly.logger.info("Waiting for the evaluation task to start... Status: %s", task_status)
            time.sleep(5)
            if time.time() - current_time > 300:  # 5 minutes timeout
                sly.logger.warning(
                    "Timeout reached while waiting for the evaluation task to start."
                )
                break

        return task_id

    def send_comparison_request(self):
        """
        Sends a request to the backend to start the evaluation process.
        """
        self.warning.hide()
        self.hide_failed_badge()
        self.hide_running_badge()
        self.hide_finished_badge()
        if not self.eval_dirs or len(self.eval_dirs) < 2:
            sly.logger.warning("Not enough evaluation directories provided for comparison.")
            self.show_failed_badge()
            self.warning.show()
            return
        self.show_running_badge()
        try:
            # raise RuntimeError("This is a test error to check error handling.")
            task_id = self.run_evaluator_session_if_needed()
            request_data = {
                "eval_dirs": self.eval_dirs,
            }
            response = self.api.task.send_request(
                task_id, self.COMPARISON_ENDPOINT, data=request_data
            )
            if "error" in response:
                raise RuntimeError(f"Error in evaluation request: {response['error']}")
            sly.logger.info("Evaluation request sent successfully.")
            self.result_comparison_dir = response.get("data")
            self.result_comparison_link = self._get_url_from_lnk_path(
                self.result_comparison_dir + "/Model Comparison Report.lnk"
            )
            # @ todo: find the best checkpoint from the evaluation results
            # self._update_properties()
            for cb in self._finish_callbacks:
                cb(self.result_comparison_dir, self.result_comparison_link)
            self.show_finished_badge()
            self.hide_running_badge()
        except:
            sly.logger.error("Evaluation failed.", exc_info=True)
            self.show_failed_badge()
            self.hide_running_badge()

    def get_available_agent_id(self) -> int:
        agents = self.api.agent.get_list_available(self.team_id, True)
        return agents[0].id if agents else None

    def on_finish(self, fn):
        """
        Decorator to register a callback to be called with result_dir when comparison finishes.
        """
        self._finish_callbacks.append(fn)
        return fn

    def _get_url_from_lnk_path(self, remote_lnk_path) -> str:
        if not self.api.file.exists(self.team_id, remote_lnk_path):
            sly.logger.warning(
                f"Link file {remote_lnk_path} does not exist in the benchmark directory."
            )
            return ""

        self.api.file.download(self.team_id, remote_lnk_path, "./model_evaluation_report.lnk")
        with open("./model_evaluation_report.lnk", "r") as file:
            base_url = file.read().strip()

        sly.fs.silent_remove("./model_evaluation_report.lnk")

        return sly.utils.abs_url(base_url)

    def show_running_badge(self):
        """
        Updates the card to show that the evaluation is running.
        """
        self.card.update_badge_by_key(
            key="In Progress", label="⚡", plain=True, badge_type="warning"
        )
        self._run_btn.disable()

    def hide_running_badge(self):
        """
        Hides the running badge from the card.
        """
        self.card.remove_badge_by_key(key="In Progress")
        self._run_btn.enable()

    def show_finished_badge(self):
        """
        Updates the card to show that the comparison is finished.
        """
        self.card.update_badge_by_key(key="Finished", label="✅", plain=True, badge_type="success")
        self._run_btn.disable()

    def hide_finished_badge(self):
        """
        Hides the finished badge from the card.
        """
        self.card.remove_badge_by_key(key="Finished")
        self._run_btn.enable()

    def show_failed_badge(self):
        """
        Updates the card to show that the comparison has failed.
        """
        self.card.update_badge_by_key(key="Failed", label="❌", plain=True, badge_type="error")
        self.failed_notification.show()

    def hide_failed_badge(self):
        """
        Hides the failed badge from the card.
        """
        self.card.remove_badge_by_key(key="Failed")
        self.failed_notification.hide()

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

    def _get_default_icon(self) -> Icons:
        icon_color, bg_color = self._random_pretty_color()
        return Icons(
            class_name="zmdi zmdi-compare",
            color=icon_color,
            bg_color=bg_color,
        )

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

    def _update_properties(self):
        new_propetries = [
            {
                "key": "Best model",
                "value": self.result_best_checkpoint or "Unknown",
                "highlight": True,
                "link": False,
            },
            {
                "key": "Automatic re-deployment",
                "value": "✔️" if self.is_automated else "✖",
                "highlight": False,
                "link": False,
            },
        ]
        for prop in new_propetries:
            self.card.update_property(**prop)
