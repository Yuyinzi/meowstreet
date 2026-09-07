from collections.abc import Iterable, Mapping


_PROVIDER_ORDER = ("tavily", "native_search", "ddgs")


class SearchRouter:
    def __init__(self, config: Mapping[str, str] | None, providers: Iterable):
        self.config = dict(config or {})
        self._providers = {}
        for provider in providers:
            name = getattr(provider, "name", None)
            if name and name not in self._providers:
                self._providers[name] = provider
        self._disabled = set()

    def disable(self, name: str) -> None:
        if name in self._providers:
            self._disabled.add(name)

    def disabled(self) -> set[str]:
        return set(self._disabled)

    def unavailable(self) -> list[str]:
        primary = str(self.config.get("provider", "auto")).strip().lower()
        if primary == "auto":
            return []
        provider = self._providers.get(primary)
        if provider is None or not _ready(provider):
            return [primary]
        return []

    def provider_chain(self) -> list:
        primary = str(self.config.get("provider", "auto")).strip().lower() or "auto"
        fallback = str(self.config.get("fallback", "auto")).strip().lower() or "auto"
        if primary == "auto":
            names = list(_PROVIDER_ORDER)
        else:
            names = [primary]
            if fallback == "auto":
                names.extend(name for name in _PROVIDER_ORDER if name != primary)
            elif fallback == "ddgs":
                names.append("ddgs")
        result = []
        seen = set()
        for name in names:
            if name in seen or name in self._disabled:
                continue
            seen.add(name)
            provider = self._providers.get(name)
            if provider is not None and _ready(provider):
                result.append(provider)
        return result


def _ready(provider) -> bool:
    try:
        return bool(getattr(provider, "ready", False))
    except Exception:
        return False
