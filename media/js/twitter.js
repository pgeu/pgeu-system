/* Silly javascript lacks basic functionality */
function LeadingZero(s) {
    let ss = s;
    while (ss.toString().length < 2) {
        ss = '0' + ss;
    }
    return ss;
}
function DateString(origdate) {
    /*
      Get the date in the server timezone. Javascript is basically uncapable of this, but we can
      add a fixed offset, so let's do that.
      Also note that date.getTimezoneOffset() returns the inverse of the actual timezone offset.
    */
    let date = new Date(origdate.getTime() + (origdate.getTimezoneOffset()+parseInt(parseInt($('body').data('tzoffset'))))*60000);
    return date.getFullYear()+'-'+LeadingZero(date.getMonth()+1)+'-'+LeadingZero(date.getDate())+' '+LeadingZero(date.getHours())+':'+LeadingZero(date.getMinutes());
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

function reset_state() {
    $('#statusdiv').hide();
    $('#queuerow').hide();
    $('#incomingrow').hide();
    $('#buttonrow').show();
}

function add_queue_entry_html(row, d, modbuttons, panelstyle) {
    var e = $('<div/>').addClass('queueentry panel panel-' + panelstyle);
    e.append($('<div/>').addClass('panel-heading').text(d['time']));
    var cdiv = $('<div/>').addClass('panel-body').text(d['txt']);
    if (d['hasimage']) {
	cdiv.append($('<img/>').addClass('preview-image').attr('src', '?op=thumb&id=' + d['id']));
    }
    e.append(cdiv);
    fdiv = $('<div/>').addClass('panel-footer');
    let dstr = d['delivered'] ? ' Delivery complete.':'';
    fdiv.append($('<p/>').text('Queued by ' + d['author'] + ' for ' + d['time'] + '.' + dstr));
    if (modbuttons) {
       fdiv.append($('<button/>').data('tid', d['id']).addClass('btn btn-primary btn-sm approve-button').text('Approve'));
       fdiv.append($('<button/>').data('tid', d['id']).addClass('btn btn-default btn-sm discard-button').text('Discard'));
    }
    e.append(fdiv);

    row.append(e);
}


function add_incoming_entry_html(row, d, dismissbutton, panelstyle) {
    var e = $('<div/>').addClass('incomingentry panel panel-' + panelstyle).data('replyid', d['id']).data('replyto', d['author']).data('replymaxlength', d['replymaxlength']);
    e.append($('<div/>').addClass('panel-heading').text('Posted by @' + d['author'] + ' (' + d['authorfullname'] + ') at ' + d['time']));
    var cdiv = $('<div/>').addClass('panel-body').text(d['txt']);
    if (d['media']) {
	$.each(d['media'], function(i, o) {
	    cdiv.append($('<img/>').addClass('preview-image').attr('src', o + '?name=thumb'));
	});
    }
    e.append(cdiv);
    fdiv = $('<div/>').addClass('panel-footer');
    fdiv.append($('<button/>').data('tid', d['id']).addClass('btn btn-primary btn-sm reply-button').text('Reply'));
    if (dismissbutton) {
       fdiv.append($('<button/>').data('tid', d['id']).addClass('btn btn-default btn-sm dismiss-incoming-button').text('Dismiss'));
    }
    var rtbtn = $('<button/>').data('tid', d['id']).addClass('btn btn-default btn-sm retweet-button');
    if (d['rt'] == 0) {
	rtbtn.text('Repost');
    }
    else {
	rtbtn.text('Reposted');
	rtbtn.attr('disabled', 'disabled');
    }
    fdiv.append(rtbtn);
    fdiv.append($('<button/>').data('url', d['url']).addClass('btn btn-default btn-sm view-twitter-button').text('View on ' + d['provider']));
    e.append(fdiv);

    row.append(e);
}



var lastcheck = 0;
var lastqueue = true;
var lastincoming = true;
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
	    if (data['hasqueue'] != lastqueue) {
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
		lastqueue = data['hasqueue'];
	    }

	    if (data['hasincoming'] != lastincoming) {
		if (data['hasincoming']) {
		    $('#incomingTweetsButton').removeClass('btn-default').addClass('btn-primary');
		}
		else {
		    $('#incomingTweetsButton').removeClass('btn-primary').addClass('btn-default');
		}

		if (data['hasincoming']) {
		    if ("Notification" in window) {
			if (Notification.permission === "granted") {
			    var not = new Notification($('body').data('confname') + ": One or more incoming tweets arrived");
			}
		    }
		}
		lastincoming = data['hasincoming'];
	    }
	    lastcheck = new Date();
	}
    });
}

$(function() {
    var is_poster = $('body').data('poster');
    var is_directposter = $('body').data('directposter');
    var is_moderator = $('body').data('moderator');
    var global_maxlength = parseInt($('body').data('maxlength'));

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
        let t = DateString(new Date());
        $('#newTweetText').val('');
        $('#newTweetSchedule').val(t);
        $('#newTweetSchedule').attr('min', t);
	$('#newTweetUpload').val('');
	$('#tweetBypassApproval').prop('checked', false);
	$('#tweetLength').text('0');
	$('#newTweetModal').data('replyid', '');
	$('#newTweetModal').data('maxlength', global_maxlength);
	$('#newTweetModal').modal({});
    });

    $('#newTweetText').on('input', function() {
       let maxlength = parseInt($('#newTweetModal').data('maxlength'));

       /* Unfortunatley the input event cannot be canceled, so we have to backwards try to cut the text down */
       let l = shortened_post_length($(this).val());
       $('#tweetLength').text(l + ' of ' + maxlength);
       while (l > maxlength) {
          $(this).val($.trim($(this).val()).slice(0, -1));
	  l = shortened_post_length($(this).val());
          $('#tweetLength').text(l);
       }
    });

    $('#posttweetbutton').click(function() {
	var txt = $.trim($('#newTweetText').val());
	if (txt.length < 5) {
           alert('Tweet too short');
	   return;
        }

	var fd = new FormData();
	fd.append("op", "post");
	fd.append("txt", txt);
	fd.append("at", $('#newTweetSchedule').val());
	fd.append("bypass", (is_directposter && $('#tweetBypassApproval').is(':checked')) ? 1:0);
	if ($('#newTweetUpload')[0].files[0]) {
	    fd.append("image", $('#newTweetUpload')[0].files[0]);
	}
	if ($('#newTweetModal').data('replyid')) {
	    fd.append("replyid", $('#newTweetModal').data('replyid'));
	}

	$('#newTweetModal .disableonpost').attr("disabled", true);
	$.ajax({
	    "method": "POST",
	    "dataType": "json",
	    "url": ".",
	    data: fd,
	    processData: false,
	    contentType: false,
	    success: function(data, status, xhr) {
		$('#newTweetModal .disableonpost').removeAttr("disabled");
		if ('error' in data) {
		    alert(data['error']);
		}
		else {
		    $('#newTweetModal').modal('hide');
		    showstatus('Tweet queued', 'success');
		}
		check_queue();

		if ($('#newTweetModal').data('replyid')) {
		    /* If we did a reply we should remove it from the incoming queue */
		    $('#incomingrow .incomingentry').each(function () {
			if ($(this).data('replyid') == $('#newTweetModal').data('replyid')) {
			    $(this).hide('fast', function() { e.remove(); });
			}
		    });
		};
	    },
	    error: function(xhr, status, thrown) {
		alert('Error posting tweet: ' + xhr.status);
	    }
	});
    });

    /*
     * Queued outgoing tweets
     */
    $('#tweetQueueButton').click(function() {
	$.ajax({
	    "method": "GET",
	    "data": {
		"op": "queue",
	    },
	    success: function(data, status, xhr) {
		var t = (new Date()).toLocaleTimeString(navigator.language, {hour: '2-digit', minute:'2-digit', second: '2-digit', hour12: false}) + ' (' + Intl.DateTimeFormat().resolvedOptions().timeZone + ')';

		/* Remove old entries */
		$('#queuerow .queueentry').remove();

		var row = $('#queuerow');
		row.append($('<div/>').addClass('well sectionwell queueentry').text('Moderation queue at ' + t));
		$.each(data['queue'], function(i, d) {
		    add_queue_entry_html(row, d, is_moderator, 'primary');
		});
		row.append($('<div/>').addClass('well sectionwell queueentry').text('Latest posts at ' + t));
		$.each(data['latest'], function(i, d) {
		    add_queue_entry_html(row, d, false, 'info');
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
    // End of tweet outgoing queue

    /*
     * Incoming tweets
     */
    $('#incomingTweetsButton').click(function() {
	$.ajax({
	    "method": "GET",
	    "data": {
		"op": "incoming",
	    },
	    success: function(data, status, xhr) {
		var t = (new Date()).toLocaleTimeString(navigator.language, {hour: '2-digit', minute:'2-digit', second: '2-digit', hour12: false}) + ' (' + Intl.DateTimeFormat().resolvedOptions().timeZone + ')';

		/* Remove old entries */
		$('#incomingrow .incomingentry').remove();

		var row = $('#incomingrow');
		row.append($('<div/>').addClass('well sectionwell incomingentry').text('Incoming tweets at ' + t));
		$.each(data['incoming'], function(i, d) {
		    add_incoming_entry_html(row, d, is_moderator, 'primary');
		});
		row.append($('<div/>').addClass('well sectionwell incomingentry').text('Processed incoming at ' + t));
		$.each(data['incominglatest'], function(i, d) {
		    add_incoming_entry_html(row, d, false, 'info');
		});

		$('#buttonrow').hide();
		$('#incomingrow').show();
	    },
	    error: function(xhr, status, thrown) {
		show_ajax_error('getting queue', xhr);
	    },
	});
    });

    $(document).on('click', 'button.dismiss-incoming-button', function(e) {
	var btn = $(this);

	if (!confirm('Are you sure you want to dismiss this tweet without a reply?')) {
	    return;
	}

	$.ajax({
	    "method": "POST",
	    "dataType": "json",
	    "url": ".",
	    "data": {
		"op": 'dismissincoming',
		"id": $(this).data('tid'),
	    },
	    success: function(data, status, xhr) {
		if ('error' in data) {
		    alert(data['error']);
		    return;
		}

		var e = btn.parent().parent();
		e.hide('fast', function() { e.remove(); });
	    },
	    error: function(xhr, status, thrown) {
		alert('Error updating status: ' + xhr.status);
	    },
	});
    });

    $(document).on('click', 'button.retweet-button', function(e) {
	var btn = $(this);

	if (!confirm('Are you sure you want to repost this?')) {
	    return;
	}

	$.ajax({
	    "method": "POST",
	    "dataType": "json",
	    "url": ".",
	    "data": {
		"op": 'retweet',
		"id": $(this).data('tid'),
	    },
	    success: function(data, status, xhr) {
		if ('error' in data) {
		    alert(data['error']);
		    return;
		}

		btn.text('Reposted');
		btn.attr('disabled', 'disabled');
	    },
	    error: function(xhr, status, thrown) {
		alert('Error updating status: ' + xhr.status);
	    },
	});
    });

    $(document).on('click', 'button.view-twitter-button', function(e) {
	window.open($(this).data('url'));

    });

    $(document).on('click', 'button.reply-button', function(e) {
	var btn = $(this);

	var replyto = $(this).parent().parent().data('replyto');
        $('#newTweetText').val('@' + replyto + ' ');
	$('#newTweetUpload').val('');
	$('#tweetBypassApproval').prop('checked', false);
	$('#tweetLength').text('0');
	$('#newTweetModal').data('replyid', $(this).parent().parent().data('replyid'));
	$('#newTweetModal').data('maxlength', $(this).parent().parent().data('replymaxlength'));
	$('#newTweetModal').modal({});
    });

    // End of tweet incoming queue

    if ("Notification" in window) {
	if (Notification.permission === "default") {
	    /* Have not asked before, so ask now! */
	    Notification.requestPermission().then(function (permission) {
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
});

/*
 * Functions to check length of social media posts, by adjusting for size of
 * URLs.
 * Number and regex should be kept in sync with js/admin.js
 */
const _re_urlmatcher = new RegExp('\\bhttps?://\\S+', 'ig');
const _url_shortened_len = 23;

function shortened_post_length(p) {
    return p.replace(_re_urlmatcher, 'x'.repeat(_url_shortened_len)).length;
}
