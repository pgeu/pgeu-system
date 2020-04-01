function confirmClose() {
   return confirm('Are you sure you want to close this entry?\n\nOnce closed, an entry cannot be reopened!');
}
function confirmDelete() {
   return confirm('Are you sure you want to delete this entry?\n\nUnless this is the very last item in the year, the sequence number will *not* be reused!');
}
function confirmNew() {
   return confirm('Are you sure you want to create a new entry?\n\nA new, empty, entry will be created immediately, and you have to fill it out with information. Until you do so, the database contents will be incomplete.');
}

function recalculate_sums() {
      var debit=0, credit=0;
      $('.debitbox').each(function(){ debit += Number($(this).val()); });
      $('.creditbox').each(function(){ credit += Number($(this).val()); });
      $('#debittotal').text(debit.toFixed(2));
      $('#credittotal').text(credit.toFixed(2));
      $('#difftotal').text((debit-credit).toFixed(2));
}

function _do_search(searchstr) {
   if (document.location.href.indexOf('?') > 0) {
      document.location.href=document.location.href + '&search=' + searchstr;
   } else {
      document.location.href=document.location.href + '?search=' + searchstr;
   }
}

function search() {
   _do_search($('#searchentry').val());
}
function resetSearch() {
   _do_search('');
}

$(function() {
   $('#searchentry').keypress(function(e) {
      if (e.which == 13) {
         search();
      }
   });
   $('input.datepicker').datepicker({
      'dateFormat': 'yy-mm-dd',
   });
   $('.dropdownbox').selectize({selectOnTab: false});
   $('.debitbox, .creditbox').change(function() {
      if ($(this).val() != '') {
         $(this).val(Number($(this).val()).toFixed(2));
      }
      recalculate_sums();
   });
   $('.debitbox, .creditbox').keypress(function(e) {
      if (e.which == 37) { // %-sign
         if ($(this).hasClass('debitbox')) {
            debitbox = $(this);
            creditbox = $(this).parent().next().find('.creditbox');
         } else {
            creditbox = $(this);
            debitbox = $(this).parent().prev().find('.debitbox');
         }

         /* Let's see if we can figure out how to balance this */
         var debit=0, credit=0;
         $(this).val('0');
         $('.debitbox').each(function(){ debit += Number($(this).val()); });
         $('.creditbox').each(function(){ credit += Number($(this).val()); });
         sum = (debit-credit).toFixed(2);
         if (sum > 0) {
            debitbox.val('');
            creditbox.val(sum);
            creditbox.focus();
         } else {
            debitbox.val(-sum);
            creditbox.val('');
            debitbox.focus();
         }
         recalculate_sums();
         return(false);
      }
   });
   recalculate_sums();
   $('.descriptionbox').focus(function() {
      if ($(this).val() == '') {
         prev = $(this).closest('tr').prev().find('.descriptionbox').val();
         if (prev) {
            $(this).val(prev);
         }
      }
   });
});
