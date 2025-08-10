function updateStatus() {
    $.ajax({
        dataType: "json",
        url: "api/status/",
        success: function(data, status, xhr) {
            $('#userName').text(data.name);
            if (!data.active) {
                showstatus(data.activestatus, 'warning');
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
    $('.found_dyn').remove();
    if (reg.note) {
        $('#scan_note').val(reg.note);
    }
    else {
        $('#scan_note').val('');
    }

    let elements = [];
    scanfields.forEach(function(a) {
        let val = reg[a[0]];
        if (val && val.length > 0) {
            elements.push($('<dt/>').text(a[1]).addClass('found_dyn'));

            if (typeof(val) == 'string') {
                let e = $('<dd/>').text(val).addClass('found_dyn');
                if (reg['highlight'].includes(a[0])) {
                    e = $(e).addClass('found_dyn_warn');
                }
                elements.push(e);
            }
            else {
                elements.push($('<dd/>').html($('<ul/>').append(
                    $.map(val, function (x) { return $('<li/>').text(x); })
                )).addClass('found_dyn'));
            }
        }
    });
    if ($('body').data('hasnote')) {
        cl.children('dt').before(elements);
    }
    else {
        cl.append(elements);
    }
}

function show_found_dialog(reg) {
    $('#foundModal').data('token', reg.token);
    $('#foundModal').data('name', reg.name);

    cl = $('#found_list');

    add_dynamic_fields(reg, cl);

    if (reg.already) {
        cl.append($('<dt/>').text(reg.already.title).addClass('found_dyn'));
        cl.append($('<dd/>').text(reg.already.body).addClass('found_dyn'));
    }

    $('#storebutton').attr('disabled', reg.already ? 'disabled' : null);

    $('#foundModal').modal({});
}

function lookup_and_complete_dialog(token) {
    $('.cancelButton').attr('disabled', 'disabled');
    $.ajax({
        dataType: "json",
        url: "api/lookup/",
        data: {"lookup": token},
        success: function(data, status, xhr) {
            show_found_dialog(data['reg'])
            reset_state();
        },
        error: function(xhr, status, thrown) {
            if (xhr.status == 404) {
                showstatus('Could not find matching entry', 'warning');
            }
            else {
                show_ajax_error('looking for reg', xhr);
            }
            reset_state();
        }
    });
}

const _tokentypes = {
    'id': 'ticket',
    'at': 'badge'
};

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
            const fulltoken = content.substring(tokenbase.length);
            const tokenparts = fulltoken.split('/');
            if (tokenparts.length != 3) {
                showstatus('Invalid token scanned.', 'danger');
                reset_state();
                return;
            }

            if (!(tokenparts[0] in _tokentypes)) {
                showstatus('Invalid token type scanned', 'danger');
                reset_state();
                return;
            }

            if (tokenparts[0] != expectedtype) {
                showstatus('You appear to have scanned a ' + _tokentypes[tokenparts[0]] + ' instead of a ' + _tokentypes[expectedtype] + '!', 'info');
                reset_state();
                return;
            }

            if (tokenparts[1] == 'TESTTESTTESTTEST') {
                showstatus('You successfully scanned the test code!', 'info');
                reset_state();
                return;
            }
        }
        /* Support for old style tokens has been dropped dropped */
        else {
            showstatus('Invalid code scanned.', 'danger');
            reset_state();
            return;
        }

        /* Else we have a code, so look it up */
        lookup_and_complete_dialog(content);
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
                    show_found_dialog(data['regs'][0]);
                    reset_state();
                    return;
                }
                if (data['regs'].length > 1) {
                    $('#selectUserBody').empty();
                    $.each(data['regs'], function(i, o) {
                        $('#selectUserBody').append($('<button class="btn btn-block" />')
                                                    .text(o.name)
                                                    .addClass(o.already ? 'btn-default' : 'btn-primary')
                                                    .click(function() {
                                                        $('#selectUserModal').modal('hide');
                                                        show_found_dialog(o);
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


    $('#storebutton').click(function() {
        let d = {
            "token": $('#foundModal').data('token'),
        }
        if ($('body').data('hasnote')) {
            d['note'] = $('#scan_note').val();
        }

        $.ajax({
            method: "POST",
            dataType: "json",
            url: "api/store/",
            data: d,
            success: function(data, status, xhr) {
                if (xhr.status == 200 || xhr.status == 201 || xhr.status == 208) {
                    /* Success! */
                    showstatus(data.message, 'success');
                    if (data.showfields) {
                        add_dynamic_fields(data['reg'], $('#completed_list'), true);
                        $('#completed_div').show();
                    }
                }
                else {
                    show_ajax_error('storing value', xhr);
                }
                $('#foundModal').modal('hide');
                reset_state(true);
            },
            error: function(xhr, status, thrown) {
                show_ajax_error('storing value', xhr);
                $('#foundModal').modal('hide');
            }
        });
    });

    if (single) {
        lookup_and_complete_dialog($('body').data('tokenbase') + $('body').data('tokentype') + '/' + $('body').data('single-token') + '/');
    }
    else {
        updateStatus();
    }
});
