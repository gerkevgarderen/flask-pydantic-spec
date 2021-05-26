import inspect
import logging

from typing import Callable, Mapping, Any, Tuple, Optional, List, Dict

from werkzeug.datastructures import MultiDict
from pydantic import BaseModel

from .types import Response, RequestBase, Request

logger = logging.getLogger(__name__)


def parse_comments(func: Callable) -> Tuple[Optional[str], Optional[str]]:
    """
    parse function comments

    First line of comments will be saved as summary, and the rest
    will be saved as description.
    """
    doc = inspect.getdoc(func)
    if doc is None:
        return None, None
    docs = doc.split("\n", 1)
    if len(docs) == 1:
        return docs[0], None
    return docs[0], docs[1].strip()


def parse_request(func: Callable) -> Mapping[str, Any]:
    """
    Generate spec from body parameter on the view function validation decorator
    """
    if hasattr(func, "body"):
        request_body = getattr(func, "body", None)
        if isinstance(request_body, RequestBase):
            result: Mapping[str, Any] = request_body.generate_spec()
        elif issubclass(request_body, BaseModel):
            result = Request(request_body).generate_spec()
        else:
            result = {}
        return result
    return {}


def parse_params(
    func: Callable,
    params: List[Mapping[str, Any]],
    models: Mapping[str, Any],
) -> List[Mapping[str, Any]]:
    """
    get spec for (query, headers, cookies)
    """
    if hasattr(func, "query"):
        model_name = getattr(func, "query").__name__
        query = models[model_name]
        for name, schema in query["properties"].items():
            params.append(
                {
                    "name": name,
                    "in": "query",
                    "schema": schema,
                    "required": name in query.get("required", []),
                }
            )

    if hasattr(func, "headers"):
        model_name = getattr(func, "headers").__name__
        headers = models[model_name]
        for name, schema in headers["properties"].items():
            params.append(
                {
                    "name": name,
                    "in": "header",
                    "schema": schema,
                    "required": name in headers.get("required", []),
                }
            )

    if hasattr(func, "cookies"):
        model_name = getattr(func, "cookies").__name__
        cookies = models[model_name]
        for name, schema in cookies["properties"].items():
            params.append(
                {
                    "name": name,
                    "in": "cookie",
                    "schema": schema,
                    "required": name in cookies.get("required", []),
                }
            )

    return params


def parse_resp(func: Callable, code: int) -> Mapping[str, Mapping[str, Any]]:
    """
    get the response spec

    If this function does not have explicit ``resp`` but have other models,
    a ``Validation Error`` will be append to the response spec. Since
    this may be triggered in the validation step.
    """
    responses: Dict[str, Any] = {}
    if hasattr(func, "resp"):
        responses = getattr(func, "resp", {}).generate_spec()

    if str(code) not in responses and has_model(func):
        responses[str(code)] = {"description": "Validation Error"}

    return responses


def has_model(func: Callable) -> bool:
    """
    return True if this function have ``pydantic.BaseModel``
    """
    if any(hasattr(func, x) for x in ("query", "json", "headers")):
        return True

    if hasattr(func, "resp") and getattr(func, "resp").has_model():
        return True

    return False


def parse_name(func: Callable) -> str:
    """
    the func can be

        * undecorated functions
        * decorated functions
        * decorated class methods
    """
    return func.__name__


def default_before_handler(
    req: Request, resp: Response, req_validation_error: Any, instance: BaseModel
) -> None:
    """
    default handler called before the endpoint function after the request validation

    :param req: request provided by the web framework
    :param resp: response generated by Flask_Pydantic_Spec that will be returned
        if the validation error is not None
    :param req_validation_error: request validation error
    :param instance: class instance if the endpoint function is a class method
    """
    if req_validation_error:
        logger.info(
            "Validation Error",
            extra={
                "spectree_model": req_validation_error.model.__name__,
                "spectree_validation": req_validation_error.errors(),
            },
        )


def default_after_handler(
    req: Request, resp: Response, resp_validation_error: Any, instance: BaseModel
) -> None:
    """
    default handler called after the response validation

    :param req: request provided by the web framework
    :param resp: response from the endpoint function (if there is no validation error)
        or response validation error
    :param resp_validation_error: response validation error
    :param instance: class instance if the endpoint function is a class method
    """
    if resp_validation_error:
        logger.info(
            "500 Response Validation Error",
            extra={
                "spectree_model": resp_validation_error.model.__name__,
                "spectree_validation": resp_validation_error.errors(),
            },
        )


def parse_multi_dict(input: MultiDict) -> Dict[str, Any]:
    result = {}
    for key, value in input.to_dict(flat=False).items():
        if len(value) == 1:
            result[key] = value[0]
        else:
            result[key] = value
    return result
