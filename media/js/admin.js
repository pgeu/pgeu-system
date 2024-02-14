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

  $('input[data-filter-select]').each(function() {
    /* Text field that filtes the content of a select */
    let target = $('#' + $(this).data('filter-select'));
    $(this).on('keyup', function(e) {
      let val = $(this).val().toLowerCase();
      $(target).find('option').each(function(i, e) {
        let ee = $(e);
        if (ee.text().toLowerCase().indexOf(val) >= 0) {
          ee.css('display', 'block');
        } else {
          ee.css('display', 'none');
        }
      });
      $(target).find('optgroup').each(function(i, e) {
        /* Hide any groups with no matching entries */
        $(e).css('display', $(e).find('option[style*="display: block"]').length ? 'block' : 'none');
      });
    });
    /* Trigger initial filter */
    $(this).trigger('keyup');
  });


    /*
     * PDF field editor
     */
    $('#pdf_fields_fieldlist').on('change', function(e) {
        let fieldtoadd = $(this).val();

        $('#pdf_fields_fieldlist').prop('selectedIndex', 0);

        let elem = $('<div/>');
        elem.addClass('pdf_fields_field');
        elem.text(fieldtoadd);
        $('#pdf_fields_page_area').append(elem);
        elem.fadeOut(200).fadeIn(200).fadeOut(200).fadeIn(200);
    });
    $('#pdf_fields_page_area').on('contextmenu', '.pdf_fields_field', function(e) {
        /* Sometihng nice for removal here */
        e.preventDefault();
    });
    $('#pdf_fields_page_area').on('mousedown', '.pdf_fields_field', function(e) {
        let initX = this.offsetLeft;
        let initY = this.offsetTop;
        let firstX = e.pageX;
        let firstY = e.pageY;

        e.preventDefault();
        $(this).on('mousemove', function(e) {
            $(this).css('left', initX+e.pageX-firstX + 'px');
            $(this).css('top', initY+e.pageY-firstY + 'px');

            $(this).css('background-color', _pdf_fields_overlaps_page($(this)) ? 'blue' : 'red');
        });
        $(this).on('mouseup', function(e) {
            $(this).off('mousemove');
            $(this).off('mouseup');
            $(this).off('mouseleave');
        });
        $(this).on('mouseleave', function(e) {
            $(this).off('mousemove');
            $(this).off('mouseup');
            $(this).off('mouseleave');
        });
    });
    $('button#pdf_fields_save').on('click', function(e) {
        let anyoutside = false;
        let data = {
            'fields': [],
            'fontsize': $('#pdf_fields_fontsize').val(),
        };
        $('div.pdf_fields_field').each(function(i, e) {
            let overlaps = _pdf_fields_overlaps_page($(e));
            if (overlaps) {
                data.fields.push({
                    'field': $(e).text(),
                    'page': $(overlaps).data('pagenum'),
                    'x': $(e).offset().left - $(overlaps).offset().left,
                    'y': $(e).offset().top - $(overlaps).offset().top,
                });
            }
            else {
                anyoutside = true;
                $(e).fadeOut(200).fadeIn(200).fadeOut(200).fadeIn(200);
            }
        });
        if (anyoutside) {
            alert('One or more fields are outside the pages. Cannot save.');
            return;
        }
        $.ajax({
            type: 'POST',
            url: '.',
            data: JSON.stringify(data),
            dataType: 'json',
            contentType: "application/json; charset=utf-8",
            headers: {
                'x-csrftoken': $(this).data('csrf'),
            },
            success: function(d) {
                alert('Saved.');
            },
            error: function(d) {
                alert('Failed to save: \n' + d.responseText);
            },
        });
    });
    if ($('#pdf_fields_fieldlist').length) {
        /* PDF field editor exists on htis page */
        const style = $('<style type="text/css" />');
        $('head').append(style);

        $('#pdf_fields_fontsize').on('change', function(e) {
            style.text('div.pdf_fields_field { font-size: ' + $(this).val() + 'pt;}');
        });

        $.ajax({
            type: 'GET',
            url: '?current=1',
            headers: {
                'Accept': 'application/json',
            },
            success: function(d) {
                if (d.fontsize) {
                    $('#pdf_fields_fontsize').val(d.fontsize);
                    style.text('div.pdf_fields_field { font-size: ' + d.fontsize + 'pt;}');
                }
                if (d.fields) {
                    d.fields.forEach(function(f) {
                        let elem = $('<div/>');
                        elem.addClass('pdf_fields_field');
                        elem.text(f.field);
                        elem.css('background-color', 'blue');
                        $('#pdf_fields_page_area').append(elem);

                        let page = $('#pdf_page_' + f.page);
                        elem.offset({
                            'top': page.offset().top + f.y,
                            'left': page.offset().left + f.x,
                        });
                    });
                }
            },
            error: function(d) {
                alert('Could not get current fields.');
            }
        });
    }
});

function _pdf_fields_overlaps_page(field) {
    /* Check if we're overlapping with a point */
    let overlapping = null;
    let thispos = field.offset();
    let thisheight = field.outerHeight();
    let thiswidth = field.outerWidth();
    $('div.pdf_fields_page img.pdf_page').each(function(i, e) {
        let epos = $(e).offset();
        let eheight = $(e).outerHeight();
        let ewidth = $(e).outerWidth();
        if (thispos.top > epos.top  && thispos.top+thisheight < epos.top+eheight &&
            thispos.left > epos.left && thispos.left+thiswidth < epos.left+ewidth) {
            overlapping = e;
            return;
        }
    });
    return overlapping;
}

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
    /*
     * Replace the URL shorterner pattern. Also replace \n (javascript newlines) with
     * \r\n (the newlines used in the backend), for consistent counting.
     */
    return p.replace(_re_urlmatcher, 'x'.repeat(_url_shortened_len)).replaceAll('\n', '\r\n').length;
}
