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

function reset_state() {
    $('#statusdiv').hide();
    $('#queuerow').hide();
    $('#buttonrow').show();
}

function add_queue_entry_html(row, d, modbuttons) {
    var e = $('<div/>').addClass('queueentry panel panel-primary');
    e.append($('<div/>').addClass('panel-heading').text(d['time']));
    var cdiv = $('<div/>').addClass('panel-body').text(d['txt']);
    if (d['hasimage']) {
	cdiv.append($('<img/>').addClass('preview-image').attr('src', '?op=thumb&id=' + d['id']));
    }
    e.append(cdiv);
    fdiv = $('<div/>').addClass('panel-footer');
    fdiv.append($('<p/>').text('Queued by ' + d['author'] + ' at ' + d['time']));
    if (modbuttons) {
       fdiv.append($('<button/>').data('tid', d['id']).addClass('btn btn-primary btn-sm approve-button').text('Approve'));
       fdiv.append($('<button/>').data('tid', d['id']).addClass('btn btn-default btn-sm discard-button').text('Discard'));
    }
    e.append(fdiv);

    row.append(e);
}

var lastcheck = 0;
var laststatus = true;
function check_queue() {
    if ((new Date()) - lastcheck < 1000) {
	console.log('Less than 1 second since last time, not checking queue')
	return;
    }
    $.ajax({
	"method": "GET",
	"data": {
	    "op": "hasqueue",
	},
	success: function(data, status, xhr) {
	    if (data['hasqueue'] != laststatus) {
		if (data['hasqueue']) {
		    $('#tweetQueueButton').removeClass('btn-default').addClass('btn-primary');
		}
		else {
		    $('#tweetQueueButton').removeClass('btn-primary').addClass('btn-default');
		}
		if (data['hasqueue']) {
		    if ("Notification" in window) {
			if (Notification.permission === "granted") {
			    var not = new Notification($('body').data('confname') + ": One or more tweets arrived in the queue to be processed");
			}
		    }
		}
		laststatus = data['hasqueue'];
	    }
	    lastcheck = new Date();
	}
    });
}

$(function() {
    var is_poster = $('body').data('poster');
    var is_directposter = $('body').data('directposter');
    var is_moderator = $('body').data('moderator');

    $('#loading').hide();
    reset_state();

    $('#topnavbar').click(function() {
        reset_state();
    });

    $('#statusdiv, #completed_div').click(function() {
        $('#statusdiv').hide();
        $('#completed_div').hide();
    });

    $(document).bind('ajaxStart', function() {
        $('#loading').show();
    });
    $(document).bind('ajaxStop', function() {
        $('#loading').hide();
    });

    $('#newTweetModal').on('shown.bs.modal', function() {
       $('#newTweetText').focus();
    });

    $('#newTweetButton').click(function() {
        $('#newTweetText').val('');
	$('#newTweetUpload').val('');
	$('#tweetBypassApproval').prop('checked', false);
	$('#tweetLength').text('0');
	$('#newTweetModal').modal({});
    });

    $('#newTweetText').on('input', function() {
       $('#tweetLength').text($.trim($(this).val()).length);
    });

    $('#posttweetbutton').click(function() {
	var txt = $('#newTweetText').val();
	if ($.trim(txt).length < 5) {
           alert('Tweet too short');
	   return;
        }

	var fd = new FormData();
	fd.append("op", "post");
	fd.append("txt", txt);
	fd.append("bypass", (is_directposter && $('#tweetBypassApproval').is(':checked')) ? 1:0);
	if ($('#newTweetUpload')[0].files[0]) {
	    fd.append("image", $('#newTweetUpload')[0].files[0]);
	}

	$.ajax({
	    "method": "POST",
	    "dataType": "json",
	    "url": ".",
	    data: fd,
	    processData: false,
	    contentType: false,
	    success: function(data, status, xhr) {
		if ('error' in data) {
		    alert(data['error']);
		}
		else {
		    $('#newTweetModal').modal('hide');
		    showstatus('Tweet queued', 'success');
		}
		check_queue();
	    },
	    error: function(xhr, status, thrown) {
		alert('Error posting tweet: ' + xhr.status);
	    }
	});
    });

    $('#tweetQueueButton').click(function() {
	$.ajax({
	    "method": "GET",
	    "data": {
		"op": "queue",
	    },
	    success: function(data, status, xhr) {
		var t = (new Date()).toLocaleTimeString(navigator.language, {hour: '2-digit', minute:'2-digit', second: '2-digit', hour12: false});

		/* Remove old entries */
		$('#queuerow .queueentry').remove();

		var row = $('#queuerow');
		row.append($('<div/>').addClass('well well-sm queueentry').text('Moderation queue at ' + t));
		$.each(data['queue'], function(i, d) {
		    add_queue_entry_html(row, d, is_moderator);
		});
		row.append($('<div/>').addClass('well well-sm queueentry').text('Latest posts' + t));
		$.each(data['latest'], function(i, d) {
		    add_queue_entry_html(row, d, false);
		});

		$('#buttonrow').hide();
		$('#queuerow').show();
	    },
	    error: function(xhr, status, thrown) {
		show_ajax_error('getting queue', xhr);
	    },
	});
    });

    $(document).on('click', 'button.approve-button, button.discard-button', function(e) {
	var isapprove = $(this).hasClass('approve-button');
	var btn = $(this);

	$.ajax({
	    "method": "POST",
	    "dataType": "json",
	    "url": ".",
	    "data": {
		"op": isapprove ? "approve" : "discard",
		"id": $(this).data('tid'),
	    },
	    success: function(data, status, xhr) {
		if ('error' in data) {
		    alert(data['error']);
		    return;
		}

		/* Whichever we did, this item should be removed from the queue */
		var e = btn.parent().parent();
		e.hide('fast', function() { e.remove(); });
	    },
	    error: function(xhr, status, thrown) {
		alert('Error updating status: ' + xhr.status);
	    },
	});
    });

    if ("Notification" in window) {
	console.log("A");
	if (Notification.permission === "default") {
	    console.log("B");
	    /* Have not asked before, so ask now! */
	    Notification.requestPermission().then(function (permission) {
		console.log("C");
		/* Nothing yet, but permission is persistent */
	    });
	}
    }

    $(window).on('focus', function() {
	check_queue();
    });

    check_queue();
    /* Update the buttons every 60 seconds */
    setInterval(check_queue, 60*1000);
    console.log("setit");
});
