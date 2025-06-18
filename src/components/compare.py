import time
from typing import Literal, Optional

import supervisely as sly
from supervisely.app.widgets import Button, Icons, NotificationBox, SolutionCard
from supervisely.solution.base_node import SolutionCardNode, SolutionElement


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
        self.api = api
        self.project = project_info
        self.team_id = project_info.team_id
        self.workspace_id = project_info.workspace_id
        self.title = title
        self.description = description
        self.width = width
        self.icon = icon
        self.tooltip_position = tooltip_position
        self.eval_dirs = evaluation_dirs

        self.result_comparison_dir = None
        self.result_comparison_link = None

        self.agent_id = agent_id or self.get_available_agent_id()
        if self.agent_id is None:
            raise ValueError("No available agent found. Please check your agents.")
        self._run_btn = Button(
            "Run",
            icon="zmdi zmdi-play",
            button_size="mini",
            plain=True,
            button_type="text",
        )

        @self._run_btn.click
        def run_click_cb():
            if self.evaluation_dirs is None:
                sly.logger.warning("Evaluation directories are not set. Skipping comparison.")
                return
            self.hide_failed_badge()
            self.show_running_badge()

            self.send_comparison_request(self.evaluation_dirs)

            self.hide_running_badge()

        self.show_warning = self.eval_dirs is None or len(self.eval_dirs) < 2
        if self.show_warning:
            self._run_btn.disable()

        self.failed_notification = NotificationBox(
            "Evaluation Failed",
            "Failed to run the evaluation. Please check the logs for more details.",
            box_type="error",
        )
        self.failed_notification.hide()

        self.card = self._create_card()
        self.node = SolutionCardNode(content=self.card, x=x, y=y)

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

    def _create_card(self) -> SolutionCard:
        """
        Creates and returns the SolutionCard for the Compare widget.
        """
        content = []
        if self.show_warning:
            content.append(
                NotificationBox(
                    "Not enough evaluation reports",
                    "Please select at least two evaluation reports to compare.",
                    box_type="warning",
                )
            )
        return SolutionCard(
            title=self.title,
            tooltip=self._create_tooltip(),
            content=content,
            width=self.width,
            icon=self.icon,
            tooltip_position=self.tooltip_position,
        )

    def _create_tooltip(self) -> SolutionCard.Tooltip:
        content = [self.failed_notification, self._run_btn]
        return SolutionCard.Tooltip(description=self.description, content=content)

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

    def get_available_agent_id(self) -> int:
        agents = self.api.agent.get_list_available(self.team_id, True)
        return agents[0].id if agents else None

    def on_finish(self, fn):
        """
        Decorator to register a callback to be called with result_dir when comparison finishes.
        """
        self._finish_callbacks.append(fn)
        return fn

    def send_comparison_request(self, eval_folders_teamfiles: list[str]):
        """
        Sends a request to the backend to start the evaluation process.
        """
        try:
            # raise RuntimeError("This is a test error to check error handling.")
            task_id = self.run_evaluator_session_if_needed()
            request_data = {
                "eval_dirs": eval_folders_teamfiles,
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
            for cb in self._finish_callbacks:
                cb(self.result_comparison_dir, self.result_comparison_link)
            self.show_finished_badge()
        except:
            sly.logger.error("Evaluation failed.", exc_info=True)
            self.show_failed_badge()

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
        Updates the card to show that the evaluation is finished.
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
        Updates the card to show that the evaluation has failed.
        """
        self.card.update_badge_by_key(key="Failed", label="❌", plain=True, badge_type="error")
        self.failed_notification.show()

    def hide_failed_badge(self):
        """
        Hides the failed badge from the card.
        """
        self.card.remove_badge_by_key(key="Failed")
        self.failed_notification.hide()
