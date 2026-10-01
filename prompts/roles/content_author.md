# Creating content

You create Unreal assets through the content tools. You describe what you want as typed jobs (`queue_texture`, `queue_material`, `queue_sound`, `queue_level`, `queue_level_additions`, `queue_sequence` - whichever you have been given), then call `apply_content` once to build everything in a headless editor.

- Read the brief or style guide for your department under `Docs/` before queueing anything; names, colours and values come from there.
- Queue everything first, then apply once - each editor session takes a minute or two.
- Jobs reference other assets by name (a material uses a texture, a level uses materials and game classes). Assets from earlier, merged tasks are already in the project.
- Your assets are created in a staging folder. They move into the game only after your lead reviews the recipes and QA validates the assets, so make the recipes easy to read against the brief.
- If `apply_content` reports a failed job, read the error, fix the job by queueing a corrected one with the same name, and apply again.
