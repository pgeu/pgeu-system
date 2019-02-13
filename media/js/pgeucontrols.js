$(function() {
    $('button.pgeu-datetime-set-button').on('click', function(e) {
	d = (new Date()).toISOString();
	$($('.pgeu-datetime-set-button')[0]).parent().parent().find('input').val(d.substring(0,10) + ' ' + d.substring(11,16));
    });
});
