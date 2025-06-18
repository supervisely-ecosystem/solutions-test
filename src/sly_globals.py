import supervisely as sly
from dotenv import load_dotenv

if sly.is_development():
    load_dotenv("local.env")

api = sly.Api.from_env()
team_id = sly.env.team_id()

project = api.project.get_info_by_id(sly.env.project_id())
custom_data = project.custom_data
collection_id = None
