$(document).ready(function() {
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

   update_sendmail_count();
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
