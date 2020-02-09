import os
import json
import logging
import copy


# XXX: keep in sync with deploystatic.py!
def deep_update_context(target, source):
    for k, v in source.items():
        if type(v) == dict:
            # If this is a dict stored in the dict
            if k not in target:
                # Target didn't have it, so copy it over
                target[k] = copy.deepcopy(v)
            elif type(target[k]) != dict:
                # Target had something but it's not a dict, so overwrite it
                target[k] = copy.deepcopy(v)
            else:
                deep_update_context(target[k], v)
        else:
            target[k] = copy.copy(v)


def _load_context_file(filename):
    try:
        with open(filename, encoding='utf8') as f:
            return json.load(f)
    except ValueError as e:
        # Malformatted JSON -- pass it through as an exception
        raise
    except Exception:
        # Any other error, just ignore it (?)
        return {}


def load_base_context(rootdir):
    if os.path.isfile(os.path.join(rootdir, 'templates/context.json')):
        return _load_context_file(os.path.join(rootdir, 'templates/context.json'))
    return {}


def load_override_context(rootdir):
    # Load contexts in override directory, if any
    c = {}
    if os.path.isdir(os.path.join(rootdir, 'templates/context.override.d')):
        for fn in sorted(os.listdir(os.path.join(rootdir, 'templates/context.override.d'))):
            if fn.endswith('.json'):
                try:
                    with open(os.path.join(rootdir, 'templates/context.override.d', fn)) as f:
                        deep_update_context(c, json.load(f))
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        'Failed to load context file {}: {}'.format(os.path.join(rootdir, 'templates/context.override.d', fn), e)
                    )
    return c


def update_with_override_context(context, rootdir):
    deep_update_context(context, load_override_context(rootdir))
