import functools
import re
from inspect import cleandoc

import Options
from worlds.AutoWorld import AutoWorldRegister

KH1_GAME_NAME = 'Kingdom Hearts'

def _slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

def _describe_option(key, option):
    """Serializes one option class into the shape generate_a_seed.html renders.
    Returns None for option types the website form has no control for (e.g.
    the dict/list options in "Item & Location Options")."""
    setting = {
        'key': key,
        'label': getattr(option, 'display_name', key),
        'description': cleandoc(option.__doc__ or ''),
        'rich_text_doc': bool(option.rich_text_doc),
    }
    # Toggle and Choice are both NumericOptions with a name_lookup; their YAML
    # value is the option key (e.g. "true", "lucky_emblems"), not the int.
    if issubclass(option, (Options.Toggle, Options.Choice)):
        setting['type'] = 'select'
        setting['options'] = [
            {'value': name, 'text': option.get_option_name(value)}
            for value, name in sorted(option.name_lookup.items())
        ]
        setting['default'] = option.name_lookup[option.default]
    elif issubclass(option, Options.Range):
        setting['type'] = 'range'
        setting['min'] = option.range_start
        setting['max'] = option.range_end
        setting['default'] = option.default
        if issubclass(option, Options.NamedRange):
            setting['special'] = [
                {'value': value, 'text': name}
                for name, value in option.special_range_names.items()
            ]
    else:
        return None
    return setting

@functools.cache
def get_kh1_options_schema():
    """Builds the generate-a-seed settings schema straight from the installed
    KH1 world's option groups, so the website form always matches the apworld
    version this backend generates with. Cached since the world can't change
    without a reload of the web app."""
    world = AutoWorldRegister.world_types[KH1_GAME_NAME]
    # AP's every-game options (progression_balancing, accessibility) are left to
    # their defaults rather than exposed on the website form.
    common_option_keys = set(Options.CommonOptions.type_hints)
    tabs = []
    for group_name, group_options in Options.get_option_groups(world, Options.Visibility.simple_ui).items():
        settings = [s for s in (_describe_option(key, option) for key, option in group_options.items()
                                if key not in common_option_keys) if s]
        if settings:
            tabs.append({'slug': _slugify(group_name), 'name': group_name, 'settings': settings})
    return {
        'game': KH1_GAME_NAME,
        'world_version': world.world_version.as_simple_string(),
        'tabs': tabs,
    }
