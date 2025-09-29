class _StaticCommandStrategy(CommandBuilder):
    """Command builder returning a static command tuple."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        return tuple(self.base)


def static_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder that yields *base* without modification."""

    base_args = _require_string_sequence(config, "base", context="command_static")
    return _StaticCommandStrategy(base=base_args)


def gofmt_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for gofmt."""

    return static_command(config)


def cargo_fmt_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for cargo fmt."""

    return static_command(config)


def cargo_clippy_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for cargo clippy."""

    return static_command(config)


def mdformat_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for mdformat."""

    return static_command(config)
