/* Shared scripts for pgeu conference frontends */


/* Call for papers form */
async function addSpeakerClick(event) {
  event.preventDefault();

  let email = prompt('Enter the email address of the speaker to add.');
  if (email) {
    let ul = event.target.previousElementSibling;
    let select = ul.previousElementSibling;

    let res = await fetch('/events/' + select.dataset.urlname + '/callforpapers/lookups/speakers/?' + new URLSearchParams({'query': email}));
    if (res.status != 200) {
      alert('Speaker not found.\n\nNote that thee speaker must have an existing profile on this site with the given email address before they can be adde to a session.\n');
      return;
    }
    let speaker = await res.json();

    if (select.querySelector('option[value="' + speaker.id + '"]')) {
      alert('This speaker has already been added.');
      return;
    }

    let newli = document.createElement('li');
    newli.dataset.id = speaker.id;
    newli.innerHTML = speaker.name + ' (<a class="pgeu-speaker-remove" href=#"#>remove</a>)';
    ul.appendChild(newli);

    let newoption = document.createElement('option');
    newoption.value = speaker.id;
    newoption.selected = true;
    select.appendChild(newoption);
  }

  return false;
}

function removeSpeakerClick(event) {
  if (event.target.tagName == 'A' && event.target.classList.contains('pgeu-speaker-remove')) {
    event.preventDefault();

    let idtoremove = event.target.parentNode.dataset.id;

    if (!confirm('Are you sure you want to remove this speaker?')) {
      return;
    }

    /* <a>.<li>.<ul>.<select> */
    event.target.parentNode.parentNode.previousElementSibling.querySelector('option[value="' + idtoremove + '"]').remove();

    event.target.parentNode.remove();

    alert('Speaker removed. You have to also save the form to make it permanent.');
  }
}

/*
 * Global event listeners
 */
document.addEventListener('DOMContentLoaded', (event) => {
  /* Call for papers form */
  document.querySelectorAll("button.pgeu-speaker-add").forEach((button) => {
    button.addEventListener('click', addSpeakerClick);
  });
  document.querySelectorAll("ul.pgeu-speaker-list").forEach((ul) => {
    ul.addEventListener('click', removeSpeakerClick);
  });

  /* Invoice confirm */
  document.querySelectorAll("input.pgeu-confirm-invoice-button").forEach((input) => {
    input.addEventListener('click', (event) => {
      if (!confirm('Once you proceed to payment, an invoice will be generated for your ' + event.target.dataset.confirmwhat + ', and you will no longer be able to change it.\n\nThis invoice will be addressed to the person, company and address specified in the registration - please take a moment to review those fields if you need to.\n\nThe invoice will be delivered as a PDF in your browser, no paper invoice will be sent.\n\Are you sure you want to proceed to payment?')) {
        event.preventDefault();
      }
    });
  });

  /* Registration cancellation */
  document.querySelectorAll("input.pgeu-confirm-cancel-registration-button").forEach((input) => {
    input.addEventListener('click', (event) => {
      if (!confirm('Are you sure you want to cancel and remove your registration?')) {
        event.preventDefault();
      }
    });
  });

  /* Generic page-level alerts */
  document.querySelectorAll("div.pgeu-pagealert").forEach((div) => {
    alert(div.innerText);
  });
});
