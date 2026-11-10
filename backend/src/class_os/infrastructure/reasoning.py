"""SDK settings for an explicit dispatch-time UI preference, never authority."""
import re
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from class_os.application.agent import AgentRejected


def reasoning_settings(model, effort):
    if effort is None:
        return {}
    if effort not in ('low', 'medium', 'high'):
        raise AgentRejected()
    if isinstance(model, GoogleModel) and model.model_name.startswith('gemini-3'):
        return {'google_thinking_config': {'thinking_level': effort.upper()}}
    if isinstance(model, (OpenAIChatModel, OpenAIResponsesModel)) and re.match(r'^(gpt-5|o[1-9])', model.model_name):
        return {'openai_reasoning_effort': effort}
    raise AgentRejected()
