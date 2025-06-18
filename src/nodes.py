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

eval_1 = EvaluationReportNode(
    api=g.api,
    project_info=g.project,
    title="Evaluation Report",
    description="View the evaluation report of the model.",
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
    description="View the evaluation report of the model.",
    # benchmark_dir="/model-benchmark/73_sample COCO/7956_Train YOLO v8 - v12/",
    benchmark_dir="/model-benchmark/73_sample COCO/7958_Train YOLO v8 - v12/",
    width=200,
    x=690,
    y=350,
    icon=Icons(class_name="zmdi zmdi-open-in-new", color="#FF9100", bg_color="#FFE0BC"),
)
compare = CompareNode(
    api=g.api,
    project_info=g.project,
    title="Compare Reports",
    description="Compare the evaluation results of different models.",
    width=250,
    x=520,
    y=500,
    icon=Icons(class_name="zmdi zmdi-compare", color="#1074FF", bg_color="#CEE3FF"),
    evaluation_dirs=[eval_1.benchmark_dir, eval_2.benchmark_dir],
)
comparison_result = LinkNode(
    title="Comparison Result",
    description="View the comparison of the evaluation reports.",
    link="",
    x=520,
    y=650,
    icon=Icons(class_name="zmdi zmdi-open-in-new", color="#FF00A6", bg_color="#FFBCED"),
)
comparison_result.node.disable()


@compare.on_finish
def on_finish_cb(result_dir, result_link):
    if result_link:
        comparison_result.card.link = result_link
        comparison_result.node.enable()


if sly.is_development():
    load_dotenv("secrets.env")

email_creds = SendEmailNode.EmailCredentials(
    username=getenv("EMAIL_USERNAME"),
    password=getenv("EMAIL_PASSWORD"),
)
send_email_node = SendEmailNode(
    email_creds, body="Hey, bastard!", target_addresses="germ.vorozhko@gmail.com", x=900, y=750
)

graph_builder = sly.solution.SolutionGraphBuilder(height="1100px")

# * Add nodes to the graph
graph_builder.add_node(input_project)
graph_builder.add_node(eval_1)
graph_builder.add_node(eval_2)
graph_builder.add_node(compare)
graph_builder.add_node(comparison_result)
graph_builder.add_node(send_email_node)

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
    comparison_result,
    path="grid",
)
graph_builder.add_edge(
    comparison_result,
    send_email_node,
    start_socket="right",
    end_socket="left",
    path="fluid",
    dash=True,
)

# * Build the layout
layout = graph_builder.build()
