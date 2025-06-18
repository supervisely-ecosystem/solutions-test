from typing import Literal, Optional

import supervisely as sly
from supervisely.app.widgets import Icons, SolutionCard
from supervisely.solution.base_node import SolutionCardNode, SolutionElement


class EvaluationReportNode(SolutionElement):
    def __init__(
        self,
        api: sly.Api,
        project_info: sly.ProjectInfo,
        benchmark_dir: str,
        title: str,
        description: str,
        width: int = 250,
        x: int = 0,
        y: int = 0,
        icon: Optional[Icons] = None,
        tooltip_position: Literal["left", "right"] = "right",
        display_overview: bool = True,
        *args,
        **kwargs,
    ):
        """A node that displays a model evaluation report."""
        self.api = api
        self.project = project_info
        self.team_id = project_info.team_id
        self.title = title
        self.description = description
        self.width = width
        self.icon = icon
        self.tooltip_position = tooltip_position

        self._benchmark_dir = benchmark_dir or self.get_first_valid_benchmark()
        if self._benchmark_dir is None:
            raise ValueError("No valid benchmark directory found in the project.")

        lnk_path = f"{self._benchmark_dir.rstrip('/')}/visualizations/Model Evaluation Report.lnk"
        self.url = self._get_url_from_lnk_path(lnk_path)
        self.markdown_overview = self._get_overview_markdown() if display_overview else None
        self.card = self._create_card()
        self.node = SolutionCardNode(content=self.card, x=x, y=y)
        super().__init__(*args, **kwargs)

    def _create_card(self) -> SolutionCard:
        """
        Creates and returns the SolutionCard for the Manual Import widget.
        """
        return SolutionCard(
            title=self.title,
            tooltip=self._create_tooltip(),
            width=self.width,
            tooltip_position=self.tooltip_position,
            link=self.url,
            icon=self.icon,
        )

    @property
    def benchmark_dir(self) -> str:
        """
        Returns the benchmark directory for the evaluation report.
        """
        return self._benchmark_dir

    @benchmark_dir.setter
    def benchmark_dir(self, value: str):
        """
        Sets the benchmark directory for the evaluation report.
        """
        if not value:
            raise ValueError("Benchmark directory cannot be empty.")
        self._benchmark_dir = value

    def _create_tooltip(self) -> SolutionCard.Tooltip:
        """
        Creates and returns the tooltip for the Manual Import widget.
        """
        # content = [Markdown(self.markdown_overview)] if self.markdown_overview else []
        return SolutionCard.Tooltip(
            description=self.description, properties=self._property_from_md()
        )

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

    # def _get_valid_benchmark_id(self, benchmark_id: int = None) -> int:
    #     benchmark_dir = f"/model-benchmark/{self.project.id}_{self.project.name}"
    #     benchmarks = self.api.file.listdir(self.team_id, benchmark_dir)
    #     if not benchmarks:
    #         sly.logger.warning("Project has no benchmark data.")
    #         return None

    #     for benchmark in benchmarks:
    #         if benchmark_id is not None and benchmark.startswith(f"{benchmark_id}_"):
    #             self.benchmark_dir = benchmark
    #         template_path = benchmark + "template.vue"
    #         if self.api.file.exists(self.team_id, template_path):
    #             self.benchmark_dir = benchmark
    #             return benchmark.split("_")[0]

    #     return None

    def get_first_valid_benchmark(self) -> str:
        """
        Returns the first valid benchmark directory for the project.
        """
        benchmark_dir = f"/model-benchmark/{self.project.id}_{self.project.name}"
        benchmarks = self.api.file.listdir(self.team_id, benchmark_dir)
        if not benchmarks:
            sly.logger.warning("Project has no benchmark data.")
            return None

        for benchmark in benchmarks:
            template_path = f"{benchmark}/template.vue"
            if self.api.file.exists(self.team_id, template_path):
                return benchmark

        sly.logger.warning("No valid benchmark found in the project.")
        return None

    def _get_overview_markdown(self) -> str:
        """
        Returns the overview markdown for the evaluation report.
        """
        from tempfile import TemporaryDirectory

        vis_data_dir = "{}visualizations/data/".format(self.benchmark_dir)
        for filepath in self.api.file.listdir(self.team_id, vis_data_dir):
            if "markdown_overview_markdown" in filepath:
                with TemporaryDirectory() as temp_dir:
                    local_path = f"{temp_dir}/markdown_overview.md"
                    self.api.file.download(self.team_id, filepath, local_path)
                    with open(local_path, "r") as f:
                        lines = f.readlines()
                        return "".join(lines[:-1]) if len(lines) > 1 else ""

        sly.logger.warning("No overview markdown found in the benchmark directory.")
        return None

    def _property_from_md(self):
        """
        Extracts properties from the markdown overview.
        """
        if not self.markdown_overview:
            return {}

        keys_to_ignore = [
            "Task type",
            "Ground Truth project",
            "Training dashboard",
            "Averaging across IoU thresholds",
            "Checkpoint file",
        ]

        def remove_href_from_value(value: str) -> str:
            """
            Removes any href links from the value string.
            """
            if "<a" not in value:
                return value.strip()

            start = value.find("<a")
            return value[:start].strip().rstrip(",")

        properties = []
        lines = self.markdown_overview.split("\n")
        for line in lines:
            if line.strip() == "":
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.replace("**", "").replace("-", "").strip()
                if key in keys_to_ignore:
                    continue
                value = remove_href_from_value(value)
                properties.append({"key": key, "value": value, "link": False, "highlight": False})

        return properties
