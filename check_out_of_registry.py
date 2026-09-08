import edgedash.query.ask as ask_module

ask_module.complete_json = lambda prompt, schema: {"tool": None, "params": {}, "confidence": "high"}
result = ask_module.ask("should I take a pay cut for a remote role?")
print("tool_used=", result.tool_used)
print("rows=", result.rows)
print("text=", result.text)
