from os import getenv

import supervisely as sly
from dotenv import load_dotenv
from supervisely.app.widgets import Icons
from supervisely.solution import LinkNode

import src.sly_globals as g
from src.components.compare import CompareNode
from src.components.evaluation_report import EvaluationReportNode
from src.components.send_email import SendEmailNode

input_project = sly.solution.ProjectNode(
    api=g.api,
    x=400,
    y=50,
    project_id=g.project.id,
    title="Input Project",
    description="Centralizes all incoming data. Data in this project will not be modified.",
    widget_id="input_project_widget",
)

evaluation_desc = "Quick access to the evaluation report of the model. "
eval_1 = EvaluationReportNode(
    api=g.api,
    project_info=g.project,
    title="Evaluation Report",
    description=evaluation_desc,
    benchmark_dir="/model-benchmark/73_sample COCO/7958_Train YOLO v8 - v12/",
    width=200,
    x=390,
    y=350,
    icon=Icons(class_name="zmdi zmdi-open-in-new", color="#FF5B10", bg_color="#FFCCBF"),
    tooltip_position="left",
)
eval_2 = EvaluationReportNode(
    api=g.api,
    project_info=g.project,
    title="Evaluation Report 2",
    description=evaluation_desc,
    # benchmark_dir="/model-benchmark/73_sample COCO/7956_Train YOLO v8 - v12/",
    benchmark_dir="/model-benchmark/73_sample COCO/7958_Train YOLO v8 - v12/",
    width=200,
    x=690,
    y=350,
    icon=Icons(class_name="zmdi zmdi-open-in-new", color="#FF9100", bg_color="#FFE0BC"),
)

compare_desc = "Compare evaluation results from the latest training session againt the best model reference report. "
"Helps track performance improvements over time and identify the most effective training setups. "
"If the new model performs better, it can be used to re-deploy the NN model for pre-labeling to speed-up the process."
compare = CompareNode(
    api=g.api,
    project_info=g.project,
    title="Compare Reports",
    description=compare_desc,
    x=520,
    y=500,
    evaluation_dirs=[eval_1.benchmark_dir, eval_2.benchmark_dir],
)
comparison_report = LinkNode(
    title="Comparison Report",
    description="Quick access to the most recent comparison report"
    "between the latest training session and the best model reference. "
    "Will be used to assess improvements and decide whether to update the deployed model.",
    link="",
    x=520,
    y=650,
    icon=Icons(class_name="zmdi zmdi-open-in-new", color="#FF00A6", bg_color="#FFBCED"),
    tooltip_position="left",
)
comparison_report.node.disable()


if sly.is_development():
    load_dotenv("secrets.env")

email_creds = SendEmailNode.EmailCredentials(
    username=getenv("EMAIL_USERNAME"),
    password=getenv("EMAIL_PASSWORD"),
)

send_email_desc = (
    "Sends an email summary after model comparison is complete. "
    "Includes key details about the latest training process "
    "and comparison details to help decide on the next actions."
)
send_email_node = SendEmailNode(email_creds, body="Hey!", description=send_email_desc, x=900, y=650)
send_email_node.card.disable()


@compare.on_finish
def on_finish_cb(result_dir, result_link):
    if result_link:
        comparison_report.card.link = result_link
        comparison_report.node.enable()
        send_email_node.card.enable()


graph_builder = sly.solution.SolutionGraphBuilder(height="1000px")

training_charts = LinkNode(
    title="Training Charts",
    description="View the training charts of the model.",
    link="",
    x=25,
    y=105,
    icon=Icons(class_name="zmdi zmdi-chart"),
)

checkpoint_folder = LinkNode(
    title="Checkpoints Folder",
    description="View the folder containing the model checkpoints.",
    link="",
    x=25,
    y=205,
    icon=Icons(class_name="zmdi zmdi-folder"),
)

# * Add nodes to the graph
graph_builder.add_node(input_project)
graph_builder.add_node(eval_1)
graph_builder.add_node(eval_2)
graph_builder.add_node(compare)
graph_builder.add_node(comparison_report)
graph_builder.add_node(send_email_node)
graph_builder.add_node(training_charts)
graph_builder.add_node(checkpoint_folder)

# * Add edges between nodes
graph_builder.add_edge(
    input_project,
    eval_1,
)
graph_builder.add_edge(input_project, eval_2, start_socket="right", path="grid")
graph_builder.add_edge(
    eval_1,
    compare,
    start_socket="right",
    path="grid",
)
graph_builder.add_edge(
    eval_2,
    compare,
    start_socket="left",
    path="grid",
)
graph_builder.add_edge(
    compare,
    comparison_report,
    path="grid",
)
graph_builder.add_edge(
    comparison_report,
    send_email_node,
    start_socket="right",
    end_socket="left",
    path="fluid",
    dash=True,
)
graph_builder.add_edge(
    input_project,
    training_charts,
    start_socket="left",
    end_socket="right",
    # path="grid",
)
graph_builder.add_edge(
    input_project,
    checkpoint_folder,
    start_socket="left",
    end_socket="right",
    # path="grid",
)

# * Build the layout
layout = graph_builder.build()
