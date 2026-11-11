"""Synthetic protocol-v1 echo example; standard library and canonical SDK only."""
from botagent_worker import Plugin

VERSION = "1.0.1"
plugin = Plugin()


@plugin.tool(
    name="echo",
    description="Return bounded synthetic text and this example version.",
    input_schema={"type": "object", "properties": {"text": {"type": "string", "maxLength": 200}},
                  "required": ["text"], "additionalProperties": False},
    read_only=True,
)
def echo(arguments, context):
    text = arguments.get("text")
    if set(arguments) != {"text"} or not isinstance(text, str) or len(text) > 200:
        raise ValueError("Expected bounded text only")
    return {"text": text, "prefix": context.configuration.get("prefix", "synthetic"), "version": VERSION}


@plugin.on_load
def load(context):
    pass


@plugin.on_unload
def unload(context):
    pass


if __name__ == "__main__":
    plugin.run()
