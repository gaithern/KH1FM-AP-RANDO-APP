import functools
import re
from inspect import cleandoc

import Options
from settings import get_settings
from worlds.AutoWorld import AutoWorldRegister

KH1_GAME_NAME = 'Kingdom Hearts'

RELEASE_CHOICES = [
    {'value': 'auto', 'text': 'Automatic on goal'},
    {'value': 'auto-enabled', 'text': 'Automatic on goal, manual any time'},
    {'value': 'enabled', 'text': 'Manual any time'},
    {'value': 'goal', 'text': 'Manual after goal'},
    {'value': 'disabled', 'text': 'Disabled'},
]

ITEM_CHEAT_CHOICES = [
    {'value': 'disabled', 'text': 'Disabled'},
    {'value': 'enabled', 'text': 'Enabled'},
]

HINT_COST_MIN = 0
HINT_COST_MAX = 100

LOCATION_CHECK_POINTS_MIN = 0
LOCATION_CHECK_POINTS_MAX = 100


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


def make_select_setting(key, label, description, choices, default):
    return {
        'key': key,
        'label': label,
        'description': description,
        'rich_text_doc': False,
        'type': 'select',
        'options': choices,
        'default': default,
    }


def make_range_setting(key, label, description, minimum, maximum, default):
    return {
        'key': key,
        'label': label,
        'description': description,
        'rich_text_doc': False,
        'type': 'range',
        'min': minimum,
        'max': maximum,
        'default': default,
    }


def get_server_options_schema():
    host_server_options = get_settings().server_options

    item_cheat_default = 'enabled'
    if host_server_options.disable_item_cheat:
        item_cheat_default = 'disabled'

    settings = [
        make_range_setting(
            'hint_cost',
            'Hint Cost',
            'Percent of your checks needed to earn one !hint. For example, 20 means you earn a hint '
            'for every 20% of your checks, for 5 hints in total. 0 makes hints free.',
            HINT_COST_MIN,
            HINT_COST_MAX,
            int(host_server_options.hint_cost),
        ),
        make_range_setting(
            'location_check_points',
            'Location Check Points',
            'Hint points you earn for each location you check. Hint Cost assumes 1 point per check, '
            'so 2 earns hints twice as fast. 0 means you can never earn a hint unless Hint Cost is 0.',
            LOCATION_CHECK_POINTS_MIN,
            LOCATION_CHECK_POINTS_MAX,
            int(host_server_options.location_check_points),
        ),
        make_select_setting(
            'release_mode',
            'Release Mode',
            'Release gives you every item still sitting in locations you haven\'t checked yet.',
            RELEASE_CHOICES,
            str(host_server_options.release_mode),
        ),
        make_select_setting(
            'item_cheat',
            'Item Cheat',
            'Whether you can give yourself items with !getitem.',
            ITEM_CHEAT_CHOICES,
            item_cheat_default,
        ),
    ]
    return settings


def is_allowed_choice(setting, submitted_value):
    for choice in setting['options']:
        if choice['value'] == submitted_value:
            return True
    return False


def read_select_value(setting, submitted_value):
    if not is_allowed_choice(setting, submitted_value):
        raise ValueError(f"Invalid value for {setting['label']}: {submitted_value}")
    return submitted_value


def read_range_value(setting, submitted_value):
    try:
        number = int(submitted_value)
    except ValueError:
        raise ValueError(f"{setting['label']} must be a whole number")
    if number < setting['min'] or number > setting['max']:
        raise ValueError(f"{setting['label']} must be between {setting['min']} and {setting['max']}")
    return number


def read_server_options(form):
    server_options = {}
    for setting in get_server_options_schema():
        key = setting['key']
        submitted_value = form.get(key)
        if submitted_value is None:
            continue

        if setting['type'] == 'range':
            value = read_range_value(setting, submitted_value)
        else:
            value = read_select_value(setting, submitted_value)

        if key == 'item_cheat':
            server_options['disable_item_cheat'] = value == 'disabled'
        else:
            server_options[key] = value
    return server_options
