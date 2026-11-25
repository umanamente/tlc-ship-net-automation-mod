# Working in Ship Net Automation

Read [the AI working guide](docs/ai/working-guide.md) and [local development setup](docs/maintainers/development.md). Use the repository-local Python environment and run the three commands in the working guide before calling a change ready.

Keep Lua changes scoped to observed game behavior. Check the existing tests and architecture decisions when changing automation, native objects or save behavior. Use the local rebuild command for Blender and Unreal changes. Keep the version report, game extracts and tool binaries local.
