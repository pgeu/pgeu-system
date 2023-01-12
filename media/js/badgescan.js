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
    if (xhr.responseText) {
        showstatus('Error ' + type + ': ' + xhr.responseText, 'danger');
    }
    else {
        showstatus('Error ' + type + ': ' + xhr.status, 'danger');
    }
}

function show_scan_dialog(token, data) {
    $('#badgescanModal').data('token', token);
    $('#badge_name').text(data.name);
    $('#badge_company').text(data.company);
    $('#badge_country').text(data.country);
    $('#badge_email').text(data.email);
    $('#badge_note').val(data.note);

    $('#badgescanModal').modal({});
}

function lookup_and_scan(token) {
    $('.cancelButton').attr('disabled', 'disabled');
    $.ajax({
        dataType: "json",
        url: "api/",
        data: {"token": token},
        success: function(data, status, xhr) {
            show_scan_dialog(token, data);
            reset_state();
        },
        error: function(xhr, status, thrown) {
            if (xhr.status == 404) {
                showstatus('Could not find attendee', 'warning');
            }
            else {
                show_ajax_error('looking for attendee', xhr);
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
            if (content.startsWith(tokenbase + 'at/')) {
                /* Correct token, check for test token */
                if (content == tokenbase + 'at/TESTTESTTESTTEST/') {
                    showstatus('You successfully scanned the test code!', 'info');
                    reset_state();
                    return;
                }
                /* Else it's a valid token */
            }
            else {
                if (content.startsWith(tokenbase + 'id/')) {
                    showstatus('You appear to have scanned a ticket instead of a badge!', 'info');
                }
                else {
                    showstatus('Scanned QR code is not from a correct badge', 'danger');
                }
                reset_state();
                return;
            }
        }
        else if (!content.startsWith('AT$') || !content.endsWith('$AT')) {
            if (content.startsWith('ID$'))
                showstatus('You appear to have scanned a ticket instead of a badge!', 'info');
            else
                showstatus('Scanned QR code is not from a correct badge', 'danger');
            reset_state();
            return;
        }
        if (content == 'AT$TESTTESTTESTTEST$AT') {
            showstatus('You successfully scanned the test code!', 'info');
            reset_state();
            return;
        }

        /* Else we have a code, so look it up */
        lookup_and_scan(content);
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

    $('#configureCameraButton').click(function() {
        configure_camera();
    });

    $('button.cancelButton').click(function() {
        $('div.approw').hide();
        $('div#buttonrow').show();
        reset_state();
    });

    $('#badgescanbutton').click(function() {
        $.ajax({
            method: "POST",
            dataType: "json",
            url: "api/",
            data: {
		token: $('#badgescanModal').data('token'),
		note: $('#badge_note').val(),
	    },
            success: function(data, status, xhr) {
                if (xhr.status == 201) {
                    /* Success! */
                    showstatus('Attendee ' + data.name + ' scan stored successfully.', 'success');
                }
		else if (xhr.status == 208) {
                    showstatus('Attendee ' + data.name + ' has already been stored.', 'info');
                }
                else {
                    show_ajax_error('storing scan', xhr);
                }
                $('#badgescanModal').modal('hide');
                reset_state(true);
            },
            error: function(xhr, status, thrown) {
                show_ajax_error('storing scan', xhr);
                $('#badgescanModal').modal('hide');
                reset_state(true);
            }
        });
    });

    if (single) {
        lookup_and_scan($('body').data('tokenbase') + 'at/' + $('body').data('single-token') + '/');
    }
});
