"""The chatbot: prompt, tools, model client and the tool loop. (Phase 7)

Four modules, in dependency order: ``prompts`` (pure), ``tools`` (needs a User
and a Session), ``client`` (needs the network), ``agent`` (needs all three).
``routers/chat.py`` is the only thing that imports ``agent``.
"""
