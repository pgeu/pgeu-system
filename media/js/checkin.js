function updateStatus() {
    $.ajax({
        dataType: "json",
        url: "api/status/",
        success: function(data, status, xhr) {
            $('#userName').text(data.name);
            if (!data.active) {
                showstatus('Check-in is not open!', 'warning');
            }
            else {
                $('#statusdiv').hide();
            }
        },
        error: function(xhr, status, thrown) {
            show_ajax_error('loading status', xhr);
        }
    });
}

function format_datetime(d) {
    d = new Date(d);
    s = d.toISOString();
    return s.substring(0,10) + ' ' + s.substring(11, 19);
}

function reset_state(leave_completed) {
    if (!leave_completed)
        $('#completed_div').hide();

    $('div.approw').hide();
    $('div#buttonrow').show();
    $('input[type=submit]').attr('disabled', null);
    $('.cancelButton').attr('disabled', null);
    scanner = $('#qrpreview').data('scanner');
    if (scanner) {
        scanner.stop();
    }
}

function showstatus(msg, level) {
    $('#statusdiv').text(msg);
    $('#statusdiv').attr('class', 'alert alert-' + level);
    if (level == 'success') {
        $('#statusdiv').fadeIn(200).fadeOut(200).fadeIn(200);
    } else {
        $('#statusdiv').fadeIn(200).fadeOut(200).fadeIn(200).fadeOut(200).fadeIn(200);
    }
}

function show_ajax_error(type, xhr) {
    if (xhr.status == 412) {
        /* 412 Precondition Failed is a controlled error from the backend code */
        showstatus('Error ' + type + ': ' + xhr.responseText, 'danger');
    }
    else {
        showstatus('Error ' + type + ': ' + xhr.status, 'danger');
    }
}

function add_dynamic_fields(reg, cl, regcompleted) {
    fields = [
        [reg.name, 'Name'],
        [reg.type, 'Registration type'],
        [reg.photoconsent, 'Photo consent'],
        [reg.tshirt, 'T-Shirt size']
    ];

    if (!regcompleted) {
        fields.push([reg.company, 'Company']);
        fields.push([reg.partition, 'Queue Partition']);
    }

    if (reg.additional.length > 0) {
        fields.push([
            $('<ul/>').append(
                $.map(reg.additional, function (x) { return $('<li/>').text(x); })
            ),
            'Additional options',
        ]);
    }

    fields.forEach(function(a) {
        if (a[0]) {
            cl.append($('<dt/>').text(a[1]).addClass('checkin_dyn'));;
            if (typeof(a[0]) == 'string') {
                cl.append($('<dd/>').text(a[0]).addClass('checkin_dyn'));
            }
            else {
                cl.append($('<dd/>').html(a[0]).addClass('checkin_dyn'));
            }
        }
    });
}

function show_checkin_dialog(reg) {
    $('#checkinModal').data('regid', reg.id);
    $('#checkinModal').data('name', reg.name);
    $('#checkin_name').text(reg.name);
    $('#checkin_type').text(reg.type);
    $('.checkin_dyn').remove();

    cl = $('#checkin_list');

    add_dynamic_fields(reg, cl);

    if (reg.checkedin) {
        cl.append($('<dt/>').text('Already checked in').addClass('checkin_dyn'));
        cl.append($('<dd/>').text('Attendee was checked in by ' + reg.checkedin.by + ' at ' + format_datetime(reg.checkedin.at) + '.').addClass('checkin_dyn'));
    }

    $('#checkinbutton').attr('disabled', reg.checkedin ? 'disabled' : null);

    $('#checkinModal').modal({});
}

function lookup_and_checkin_dialog(token) {
    $('.cancelButton').attr('disabled', 'disabled');
    $.ajax({
        dataType: "json",
        url: "api/lookup/",
        data: {"lookup": token},
        success: function(data, status, xhr) {
            show_checkin_dialog(data['reg'])
            reset_state();
        },
        error: function(xhr, status, thrown) {
            if (xhr.status == 404) {
                showstatus('Could not find matching attendee', 'warning');
            }
            else {
                show_ajax_error('looking for reg', xhr);
            }
            reset_state();
        }
    });
}

function setup_instascan() {
    let scanner = new Instascan.Scanner({
        video: document.getElementById('qrpreview'),
        scanPeriod: 5,
        mirror: false,
        backgroundScan: false,
    });

    $('#qrpreview').data('scanner', scanner);

    scanner.addListener('scan', function(content) {
        scanner.stop();
        const tokenbase = $('body').data('tokenbase');
        if (content.startsWith(tokenbase) && content.endsWith('/')) {
            /* New style token */
            if (content.startsWith(tokenbase + 'id/')) {
                /* Correct token, check for test token */
                if (content == tokenbase + 'id/TESTTESTTESTTEST/') {
                    showstatus('You successfully scanned the test code!', 'info');
                    reset_state();
                    return;
                }
                /* Else it's a valid token */
            }
            else {
                if (content.startsWith(tokenbase + 'at/')) {
                    showstatus('You appear to have scanned a badge instead of a ticket!', 'info');
                }
                else {
                    showstatus('Scanned QR code is not from a correct ticket', 'danger');
                }
                reset_state();
                return;
            }
        }
        else if (!content.startsWith('ID$') || !content.endsWith('$ID')) {
            if (content.startsWith('AT$'))
                showstatus('You appear to have scanned a badge instead of a ticket!', 'info');
            else
                showstatus('Scanned QR code is not from a correct ticket', 'danger');
            reset_state();
            return;
        }
        if (content == 'ID$TESTTESTTESTTEST$ID') {
            showstatus('You successfully scanned the test code!', 'info');
            reset_state();
            return;
        }
        /* Else we have a code, so look it up */
        lookup_and_checkin_dialog(content);
    });

    Instascan.Camera.getCameras().then(function(allcameras) {
        $('#qrpreview').data('allcameras', allcameras);
        if (allcameras.length == 0) {
            /* No cameras, so turn off scanning */
            $('#scanButton').hide();
            return;
        }
        else if (allcameras.length == 1 ||
                 navigator.userAgent.toLowerCase().indexOf('firefox/') > -1
                ) {
            /*
             * Only one camrera, or firefox. In firefox, the camera is picked
             * in the browser "do you want to share your camera" dialog and can't
             * be controlled beyond that from js.
             */
            $('#configureCameraButton').hide();
            $('#qrpreview').data('cameraid', allcameras[0].id);
            return;
        }

        if (localStorage.cameraname) {
            $('#qrpreview').data('cameraid', localStorage.cameraid);
        }
        else {
            /* No camera is configured, so default to the first one */
            $('#qrpreview').data('cameraid2', allcameras[0].id);
        }
    }).catch(e => {
        console.log('Exception setting up camera: ' + e);
        $('#scanButton').hide();
        $('#configureCameraButton').hide();
    });
}

function configure_camera() {
    $('#selectCameraBody').empty();
    $.each($('#qrpreview').data('allcameras'), function(i, c) {
        $('#selectCameraBody').append($('<button class="btn btn-block" />')
                                      .text(c.name)
                                      .addClass(localStorage.cameraid == c.id ? 'btn-primary' : 'btn-default')
                                      .data('dismiss', 'modal')
                                      .click(function() {
                                          localStorage.cameraid = c.id;
                                          $('#qrpreview').data('cameraid', c.id);
                                          $('#qrpreview').data('scanner').stop();
                                          $('#selectCameraModal').modal('hide');
                                      })
                                     );
    });
    $('#selectCameraModal').modal({});
}

function start_scanning() {
    scanner = $('#qrpreview').data('scanner');
    scanner.stop();

    id = $('#qrpreview').data('cameraid');
    $.each($('#qrpreview').data('allcameras'), function (i,c) {
        if (c.id == id) {
            scanner.start(c);
        }
    });
}

function load_stats() {
    $('#statsTable').empty();
    $.ajax({
        dataType: "json",
        url: "api/stats/",
        success: function(data, status, xhr) {
            $.each(data, function(i, sect) {
                hdr = $('<tr/>');
                $.each(sect[0], function(i, hrow) {
                    hdr.append($('<th/>').text(hrow));
                });
                $('#statsTable').append(hdr);

                $.each(sect[1], function(i, row) {
                    tr = $('<tr/>')
                    $.each(row, function(i, col) {
                        tr.append($('<td/>').text(col === null ? '' : col));
                    });
                    $('#statsTable').append(tr);
                });
            });
        },
        error: function(xhr, status, thrown) {
            show_ajax_error('loading stats', xhr);
            reset_state();
        }
    });
}

$(function() {
    $('#loading').hide();
    reset_state();

    const single = $('body').data('single') == "1";

    if (!single) {
        setup_instascan();
    }

    $('#topnavbar').click(function() {
        reset_state();
    });

    $('#statusdiv, #completed_div').click(function() {
        $('#statusdiv').hide();
        $('#completed_div').hide();
    });

    $(document).bind('ajaxSuccess', function() {
        t = (new Date()).toLocaleTimeString(navigator.language, {hour: '2-digit', minute:'2-digit', second: '2-digit', hour12: false});
        $('#lastajax').text(t);
    });
    $(document).bind('ajaxStart', function() {
        $('#loading').show();
    });
    $(document).bind('ajaxStop', function() {
        $('#loading').hide();
    });

    $('#scanButton').click(function() {
        $('#completed_div').hide();
        $('div.approw').hide();
        $('#scanrow').show();
        start_scanning();
    });

    $('#searchButton').click(function() {
        $('#completed_div').hide();
        $('div.approw').hide();
        $('#searchinput').val('');
        $('#searchrow').show();
        $('#searchinput').focus();
    });

    $('#statsButton').click(function() {
        $('#completed_div').hide();
        $('div.approw').hide();
        $('#statsrow').show();
        load_stats();
    });

    $('#configureCameraButton').click(function() {
        configure_camera();
    });

    $('button.cancelButton').click(function() {
        $('div.approw').hide();
        $('div#buttonrow').show();
        reset_state();
    });

    $('#searchForm').submit(function() {
        var searchterm = $('#searchinput').val();
        if (searchterm.length < 2) {
            return false;
        }
        $('input[type=submit]').attr('disabled', 'disabled');
        $('.cancelButton').attr('disabled', 'disabled');
        $.ajax({
            dataType: "json",
            url: "api/search/",
            data: {"search": searchterm},
            success: function(data, status, xhr) {
                if (data['regs'].length == 1) {
                    show_checkin_dialog(data['regs'][0]);
                    reset_state();
                    return;
                }
                if (data['regs'].length > 1) {
                    $('#selectUserBody').empty();
                    $.each(data['regs'], function(i, o) {
                        $('#selectUserBody').append($('<button class="btn btn-block" />')
                                                    .text(o.name)
                                                    .addClass(o.checkedin ? 'btn-default' : 'btn-primary')
                                                    .click(function() {
                                                        $('#selectUserModal').modal('hide');
                                                        show_checkin_dialog(o);
                                                    })
                                                   );
                    });
                    $('#selectUserModal').modal({});
                    reset_state();
                    return;
                }
                /* Else no match at all */
                showstatus('No match found for ' + searchterm, 'warning');
                reset_state();
            },
            error: function(xhr, status, thrown) {
                show_ajax_error('searching', xhr);
                reset_state();
            }
        });
        return false;
    });


    $('#checkinbutton').click(function() {
        $.ajax({
            method: "POST",
            dataType: "json",
            url: "api/checkin/",
            data: {"reg": $('#checkinModal').data('regid')},
            success: function(data, status, xhr) {
                if (xhr.status == 200) {
                    /* Success! */
                    showstatus('Attendee ' + $('#checkinModal').data('name') + ' checked in successfully', 'success');
                    $('.checkin_dyn').remove();
                    add_dynamic_fields(data['reg'], $('#completed_list'), true);
                    $('#completed_div').show();
                }
                else {
                    show_ajax_error('checking in', xhr);
                }
                $('#checkinModal').modal('hide');
                reset_state(true);
            },
            error: function(xhr, status, thrown) {
                show_ajax_error('checking in', xhr);
                $('#checkinModal').modal('hide');
            }
        });
    });

    if (single) {
        lookup_and_checkin_dialog($('body').data('tokenbase') + 'id/' + $('body').data('single-token') + '/');
    }
    else {
        updateStatus();
    }
});
