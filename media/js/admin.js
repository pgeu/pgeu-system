$(document).ready(function() {
   $('.confirm-btn').on("click", function(e) {
      p = $(this).data('confirm');
      if (p)
         p += "\n\n";
      p +=  '\n\nAre you sure?';
      return confirm(p);
   });

   $('#singleuploadformfile').on('change', function(e) {
       $('#singleuploadform').submit();
   });

   $('button.singleuploadformtrigger').on('click', function(e) {
       $('#singleuploadformid').val($(this).data('formid'));
       $('#singleuploadformfile').trigger('click');
   });

   $('select[data-set-form-field]').on('change', function(e) {
       const fld = $('#' + $(this).data('set-form-field'));
       const opt = $(this).find("option:selected");
       fld.val(opt.data('value'));
       fld.prop('readonly', opt.data('lock') == '1');
   }).trigger('change');

   $('.dropdown-submenu a').on("click", function(e){
       $(this).next('ul').toggle();
       e.stopPropagation();
       e.preventDefault();
   });

    $('.btn-test-validate').on("click", function(e) {
	$.ajax({
	    'url': '?validate=1',
	    'success': function(data, status, xhr) {
		$('.test-validate-wrap').html(data.replace(/\n/g, "<br/>"));
	    },
	    'error': function(data, status, xhr) {
		alert('Error: ' + xhr);
	    }
	});
	return false;
    });
    $('input').on("change", function(e) {
	$('.btn-test-validate').attr("disabled","disabled").attr("title", "Form must be saved before it can be tested");
    });

   /* Set up mailbox checkboxes */
   $('#mailcheckboxtoggler').click(function() {
      var root = $($('#datatable').data('datatable').rows( { filter : 'applied'} ).nodes());
      if (root.find('input.mailcheckbox:checked').length == 0) {
         root.find('input.mailcheckbox').prop('checked', true);
      }
      else {
         root.find('input.mailcheckbox').prop('checked', false);
      }
      update_sendmail_count();
   });

   $('input.mailcheckbox').change(function() {
      update_sendmail_count();
   });

   $('#sendmailbutton').click(function() {
      if (!$('#datatable').data('datatable')) return;

      var nodes = $($('#datatable').data('datatable').rows().nodes()).find('input.mailcheckbox:checked');
      window.location.href='sendmail/?idlist='+nodes.map(function() {
         return this.id.substring(3); // Remove em_ at the beginning
      }).get().join();
   });

   /* Set up assignment checkboxes */
   $('#assigncheckboxtoggler').click(function() {
      var root = $($('#datatable').data('datatable').rows( { filter : 'applied'} ).nodes());
      if (root.find('input.assigncheckbox:checked').length == 0) {
         root.find('input.assigncheckbox').prop('checked', true);
      }
      else {
         root.find('input.assigncheckbox').prop('checked', false);
      }
      update_assign_count();
   });

   $('input.assigncheckbox').change(function() {
      update_assign_count();
   });

   $('a.multiassign').click(function(e) {
       var assignid = $(this).data('assignid');
       var what = $(this).parent().parent().data('what');
       var title = $(this).parent().parent().data('title');

       var nodes = $($('#datatable').data('datatable').rows().nodes()).find('input.assigncheckbox:checked');
       if (confirm('Are you sure you want to assign ' + title + ' to ' + nodes.length + ' items?')) {
	   $('#assignform_idlist').val(nodes.map(function() {
               return this.id.substring(4); // Remove ass_ at the beginning
	   }).get().join());
	   $('#assignform_what').val(what);
	   $('#assignform_assignid').val(assignid);
	   $('#assignform').submit();
       }
   });

   $('a.multiaction').click(function(e) {
       var nodes = $($('#datatable').data('datatable').rows().nodes()).find('input.assigncheckbox:checked');
       if (nodes.length == 0) return;

       var idlist = nodes.map(function() {
           return this.id.substring(4); // Remove ass_ at the beginning
       }).get();
       var idliststr = idlist.join(',');

       if (confirm('Are you sure you want to "' + e.target.innerText + '" for ' + idlist.length + ' registrations')) {
           document.location.href = $(this).data('href') + '?idlist=' + idliststr;
       }
   });

   $('a.preview-pdf-link').click(function(e) {
       var w = window.open("");
       w.document.write('<iframe width="100%" height="100%" src="data:application/pdf;base64, ' + $(e.target).data('pdf') + '"></iframe>');
   });

   $('textarea.textarea-with-charcount').on('input', function(e) {
       let n = $(this).next();
       if (!n[0].classList.contains('textarea-charcount-div')) {
           n = $('<div class="textarea-charcount-div"></div>');
           n.insertAfter(this);
       }
       let l = 0;
       if ($(this).data('length-function')) {
           l = eval($(this).data('length-function'))($(this).val());
       } else {
           l = $(this).val().length;
       }
       n.text("Current length: " + l);
   }).trigger('input');

   $('div.textarea-tagoptions-list span.tagoption').click(function (e) {
       /* Insert the text from the list of options */
       var t = $(this).text();
       var ta = $('#' + $(this).parent().data('areaid'));
       var curpos = ta.prop('selectionStart');
       var txt = ta.text();
       var outtext = txt.substring(0, curpos);
       if (outtext.substr(-1) != ' ') {
	   outtext += ' ';
       }
       outtext += t;
       remaining = txt.substring(curpos);
       if (remaining.length) {
	   outtext += ' ';
	   outtext += remaining;
       }
       ta.text(outtext);
   });

   update_sendmail_count();
   update_assign_count();
});

function update_sendmail_count() {
   if ($('#datatable').data('datatable')) {
      n = $($('#datatable').data('datatable').rows().nodes()).find('input.mailcheckbox:checked').length;
   }
   else {
      n = 0;
   }
   $('#sendmailbutton').prop('disabled', n == 0).each(function() {
      /* Wrap in a function so it doesn't break if there exists no template */
      $(this).text($('#sendmailbutton').data('template').replace('{}', n));
   });
}

function update_assign_count() {
   if ($('#datatable').data('datatable')) {
      n = $($('#datatable').data('datatable').rows().nodes()).find('input.assigncheckbox:checked').length;
   }
   else {
      n = 0;
   }
   $('#assignbutton').prop('disabled', n == 0).each(function() {
      /* Wrap in a function so it doesn't break if there exists no template */
      $(this).html($('#assignbutton').data('template').replace('{}', n) + ' <span class="caret"></span>');
   });
}


/*
 * Functions to check length of social media posts, by adjusting for size of
 * URLs.
 * Number and regex should be kept in sync with js/twitter.js and util/messaging/util.py
 */
const _re_urlmatcher = new RegExp('\\bhttps?://\\S+', 'ig');
const _url_shortened_len = 23;

function shortened_post_length(p) {
    return p.replace(_re_urlmatcher, 'x'.repeat(_url_shortened_len)).length;
}
