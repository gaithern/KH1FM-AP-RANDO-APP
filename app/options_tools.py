import functools
import re
from inspect import cleandoc

import Options
from worlds.AutoWorld import AutoWorldRegister

KH1_GAME_NAME = 'Kingdom Hearts'


def make_slug(name):
    lowercase_name = name.lower()
    dashed_name = re.sub(r'[^a-z0-9]+', '-', lowercase_name)
    return dashed_name.strip('-')


def describe_choice_option(setting, option):
    setting['type'] = 'select'
    choices = []
    for value, name in sorted(option.name_lookup.items()):
        choices.append({'value': name, 'text': option.get_option_name(value)})
    setting['options'] = choices
    setting['default'] = option.name_lookup[option.default]


def describe_range_option(setting, option):
    setting['type'] = 'range'
    setting['min'] = option.range_start
    setting['max'] = option.range_end
    setting['default'] = option.default
    if issubclass(option, Options.NamedRange):
        special_values = []
        for name, value in option.special_range_names.items():
            special_values.append({'value': value, 'text': name})
        setting['special'] = special_values


def describe_set_option(setting, option):
    setting['type'] = 'set'
    setting['options'] = list(option.valid_keys)
    setting['default'] = sorted(option.default)


def describe_option(key, option):
    display_name = getattr(option, 'display_name', key)
    description = cleandoc(option.__doc__ or '')
    setting = {
        'key': key,
        'label': display_name,
        'description': description,
        'rich_text_doc': bool(option.rich_text_doc),
    }

    if issubclass(option, (Options.Toggle, Options.Choice)):
        describe_choice_option(setting, option)
    elif issubclass(option, Options.Range):
        describe_range_option(setting, option)
    elif issubclass(option, Options.OptionSet) and option.valid_keys:
        describe_set_option(setting, option)
    else:
        return None
    return setting


@functools.cache
def get_kh1_options_schema():
    world = AutoWorldRegister.world_types[KH1_GAME_NAME]
    options_left_at_default = set(Options.CommonOptions.type_hints)
    option_groups = Options.get_option_groups(world, Options.Visibility.simple_ui)

    tabs = []
    for group_name, group_options in option_groups.items():
        settings = []
        for key, option in group_options.items():
            if key in options_left_at_default:
                continue
            setting = describe_option(key, option)
            if setting is not None:
                settings.append(setting)
        if settings:
            tabs.append({'slug': make_slug(group_name), 'name': group_name, 'settings': settings})

    return {
        'game': KH1_GAME_NAME,
        'world_version': world.world_version.as_simple_string(),
        'tabs': tabs,
    }
