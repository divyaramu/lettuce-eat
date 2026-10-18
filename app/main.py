from .api import create_app, default_extractor, default_provider
from .config import get_settings
from .store import Store

settings = get_settings()
store = Store(settings.max_members)
provider, extractor = default_provider(settings), default_extractor(settings)
app = create_app(settings, provider, extractor, store)
