function update_stats(stats) {
    var tbody = $('table#statsTable tbody');
    tbody.empty();

    $.each(stats, function(index, s) {
        var row = $('<tr/>');
        row.append($('<td/>').text(s.name));
        row.append($('<td/>').text(s.count));
        row.append($('<td/>').text(s.time));
        tbody.append(row);
    });
}

function makebutton(op, txt) {
    return $('<button/>').addClass('btn btn-primary btn-xs assignment-status btn-op').data('op', op).text(txt ? txt : op);
}

function update_slot_info(slot, regid, is_admin) {
    var masterrow = $('tr.slot-row[data-slotid="' + slot.id + '"]');
    var slotcounttd = masterrow.find('td.slot-count');
    var slotcountspan = masterrow.find('span.slot-count-val');
    var listel = masterrow.find('div.slot-volunteer-list');

    var assigned_to_slot = false;

    /* Clear out all the old entries */
    listel.empty();

    /* Slot count! */
    slotcountspan.text(slot.assignments.length);
    if (slot.assignments.length  < slot.min_staff) {
        slotcounttd.addClass('danger');
    } else {
        slotcounttd.removeClass('danger');
    }

    /* List of volunteers */
    var volsInSlot = [];
    $.each(slot.assignments, function(idx, assignment) {
        volsInSlot.push(assignment.volid);

        var row = $('<div/>').data('volid', assignment.id).addClass('row');

        /* Name of volunteer */
        row.append($('<div/>').addClass('col-md-6').text(assignment.volunteer));

        /* Label showing if confirmed or not */
        if (assignment.vol_confirmed && assignment.org_confirmed) {
            row.append($('<span/>').addClass('label label-success assignment-status').text('confirmed'));
        }
        else {
            row.append($('<span/>').addClass('label label-warning assignment-status').text('unconfirmed').attr('title', 'Awaiting ' + (assignment.vol_confirmed?'organizer':'volunteer') + ' confirmation'));
        }

        if (is_admin) {
            if (!assignment.org_confirmed) {
                /* Can be confirmed if organizers haven't done so yet */
                row.append(makebutton('confirm'));
            }
            /* Organizers can always remove an entry */
            row.append(makebutton('remove'));
        }
        else {
            if (assignment.volid == regid) {
                /* Can only modify our own entries */

                assigned_to_slot = true;

                if (!assignment.vol_confirmed) {
                    row.append(makebutton('confirm'));
                }
                if (!assignment.org_confirmed) {
                    /* Can only remove if organizers have not yet confirmed */
                    row.append(makebutton('remove'));
                }
            }
        }
        listel.append(row);
    });


    /*
     * If there is at least one spot empty in this slot, add a row for signup to
     * volunteers or adding to organizers.
     */
    if (slot.assignments.length  < slot.max_staff) {
        var row = $('<div/>').data('volid', 0).addClass('row');
        var col = $('<div/>').addClass('col-md-12');

        if (is_admin) {
            /* Administrator can add other people */
            var sel = $('<select/>').addClass('add_volunteer_dropdown form-control');
            sel.append($('<option/>').attr('value', '-1').text('* Add volunteer'));
            $.each(allVolunteers, function(idx, vol) {
                if (!volsInSlot.includes(vol.id)) {
                    sel.append($('<option/>').attr('value', vol.id).text(vol.name));
                }
            });
            col.append(sel);
        }
        else {
            if (!assigned_to_slot) {
                /* Can only add if not already added */
                col.append(makebutton('signup', 'Sign up'));
            }
        }
        row.append(col);
        listel.append(row);
    }

    /* Finally mark the row as green if it's assigned to us */
    masterrow.toggleClass('success', assigned_to_slot);
}

/* Global list of values we will be reusing */
var allVolunteers;
var is_admin;
var regid;

$(function() {
    $($(document)).on('click', '.btn-op', function(event) {
        var op = $(this).data('op');
        var slotid = $(this).parents('tr').data('slotid');
        var volid = $(this).parents('div.row').data('volid');
        $.post('api/', {
            'csrfmiddlewaretoken': $('#tblSchedule').data('csrf'),
            'op': op,
            'slotid': slotid,
            'volid': volid,
        }).success(function(data, status, xhr) {
            update_slot_info(data.slot, regid, is_admin);
            update_stats(data.stats);
        }).fail(function(xhr) {
            try {
                alert('Failed to update volunteer schedule: ' + $.parseJSON(xhr.responseText).err);
            }
            catch {
                alert('An unknown error occurred when updating volunteer schedule');
            }
        });
    });

    $(document).on('change', '.add_volunteer_dropdown', function(event) {
        if (event.target.value <= 0)
            return;
        var slotid = $(this).parents('tr').data('slotid');
        $.post('api/', {
            'csrfmiddlewaretoken': $('#tblSchedule').data('csrf'),
            'op': 'add',
            'slotid': slotid,
            'volid': event.target.value,
            'dataType': 'json',
        }).success(function(data, status, xhr) {
            update_slot_info(data.slot, regid, is_admin);
            update_stats(data.stats);
        }).fail(function(xhr) {
            try {
                alert('Failed to add volunteer: ' + $.parseJSON(xhr.responseText).err);
            }
            catch {
                alert('An unknown error occurred when adding a volunteer');
            }
            $(event.target).val(0);
        });

    });

    $.get('api/').success(function(data, status, xhr) {
        $.each(data.slots, function(idx, slot) {
            allVolunteers = data.volunteers;
            is_admin = data.meta.isadmin;
            regid = data.meta.regid;
            update_slot_info(slot, regid, is_admin);
            update_stats(data.stats);
        });
    }).fail(function(data, status, xhr) {
        alert('Failed to get volunteer slot data. Volunteer schedule will not work.');
    });
});
