var maxused = {'include': 0, 'exclude': 0};
var conferences = [];

function add_conference_picker(type, default_conf, default_filt) {
    var num = maxused[type];
    maxused[type]++;

    var sel = $('<select class="confselect noexpand" id="' + type + '_' + num + '">');
    var secspan = $('<span class="secspan"/>');
    var sel2 = $('<select class="conffilter noexpand" id="' + type + 't_' + num +'">');
    var cbcancel = $('<input type="checkbox" class="noexpand" id="' + type + '_c' + num + '">');
    var lbcancel = $('<label for="' + type + '_c' + num + '">Incl. canceled</label>');
    secspan.append(sel2).append(cbcancel).append(lbcancel);

    var el = $('<div id="' + type + 'wrap_' + num + '" class="inclexclwrapper">').append(
        sel,
        secspan,
        $('<button class="btn btn-xs pull-right" onclick="return removeFilter(\'' + type + '\',' + num + ')"><span class="glyphicon glyphicon-remove-sign"></span></button>'),
    );
    $('#' + type + '_btn').before(el);

    var current_default_filt = default_filt;

    sel.selectize({valueField: 'id', labelField: 'title', searchField: 'title'});
    sel2.selectize({valueField: 'id', labelField: 'title', searchField: 'title'});

    var filtersel = sel2[0].selectize;
    if (!default_conf) {
        secspan.hide();
    }

    sel[0].selectize.load(function(callback) {
	callback(conferences);
    });

    sel[0].selectize.on('change', function(v) {
        filtersel.disable();
        filtersel.clearOptions();
        filtersel.load(function(callback) {
            $.ajax({
                url: '/events/admin/crossmail/options/?conf=' + v,
                success: function(r) {
                    callback(r);
                    secspan.show();
                    if (current_default_filt) {
                        /* Parts 0-1 are the value for the select, part 2 controls the checkbox */
                        var pieces = current_default_filt.split(':');
                        filtersel.setValue(pieces[0] + ':' + pieces[1]);
                        cbcancel.prop('checked', pieces[2] == '1');
                        current_default_filt = null;
                    }
                    filtersel.enable();
                },
                error: function() {
                    callback();
                },
            });
        });
    });

    if (default_conf) {
        sel[0].selectize.setValue(default_conf);
    }

}

function addNewFilter(type) {
    add_conference_picker(type);
    return false;
}

function removeFilter(type, num) {
    var el = $('#' + type + 'wrap_' + num);
    el.remove();
}

function submit_form() {
    function collect(type) {
        var items = [];
        $('select[id^=' + type + '_]').each(function(i, e) {
            var conf = $(e).val();
            var filt = $('#' + e.id.replace('_', 't_')).val();
            var canc = $('#' + e.id.replace('_', '_c')).is(':checked') ? 1 : 0;
            if (conf != null && conf != '' && filt != null && filt != '') {
                items.push(conf + '@' + filt + ':' + canc);
            }
        });
        $('#id_' + type).val(items.join(';'));
    }

    collect('include');
    collect('exclude');
}

$(function() {
    function prepare_picker(type) {
        var e = $('#id_' + type);
        if (e.val()) {
            pickers = e.val().split(';');
            for (var p in pickers) {
                var pieces = pickers[p].split('@');
                add_conference_picker(type, pieces[0], pieces[1]);
            }
        } else {
            // Add an empty picker
            add_conference_picker(type);
        }
    }

    /* Get the list of conferences first */
    $.ajax({
        url: '/events/admin/crossmail/options/?conf=-1',
        success: function(r) {
	    conferences = r;
	    prepare_picker('include');
	    prepare_picker('exclude');
        },
        error: function() {
	    alert('Failed to get list of conferences');
        },
    });
});
