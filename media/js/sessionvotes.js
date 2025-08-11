document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('ajaxStatus').style.display = 'none';

  document.querySelectorAll('h3:has(label.dropdown-checkbox').forEach((h) => {
    h.addEventListener('click', (e) => {
      h.querySelector('input[type="checkbox"]').checked ^= 1;
    });
  });

  document.querySelectorAll('a.filteronly').forEach((a) => {
    a.addEventListener('click', (e) => {
      e.target.parentElement.querySelectorAll('input.filtercheck').forEach((c) => {
        c.checked = c.nextElementSibling == e.target;
      });
      e.target.parentElement.querySelector('input.filterall').checked = false;
      filter_sessions();
    });
  });

  document.querySelectorAll('input.filterall').forEach((cb) => {
    cb.addEventListener('change', (e) => {
      if (e.target.checked) {
        e.target.parentElement.querySelectorAll('input.filtercheck').forEach((c) => {
          c.checked = true;
        });
      } else {
        e.target.checked = true;
      }
      filter_sessions();
    });
  });

  document.querySelectorAll('input.filtercheck').forEach((cb) => {
    cb.addEventListener('change', (e) => {
      filter_sessions();

      /* Update the "all" checkbox if needed */
      const filterall = e.target.parentElement.querySelector('input.filterall');
      if (filterall) {
        if (e.target.parentElement.querySelectorAll('input.filtercheck:not(:checked)').length) {
          filterall.checked = false;
        } else {
          filterall.checked = true;
        }
      }
    });
  });

  document.querySelectorAll('a.sortheader').forEach((a) => {
    a.addEventListener('click', (e) => {
      /* re-sort based on this column */
      let colnum = e.target.parentElement.cellIndex;
      const numsort = e.target.classList.contains('sortnumber');
      const table = document.getElementById('votetable');
      let sortdirection = 1;

      if (e.target.dataset.sorted) {
        sortdirection = e.target.dataset.sorted * -1;
      }

      Array.from(table.tBodies).sort((a, b) => {
        if (a.classList.contains('header'))
          return -1;
        if (b.classList.contains('header'))
          return 1;
        if (numsort) {
          return (a.rows[0].cells[colnum].textContent - b.rows[0].cells[colnum].textContent) * sortdirection;
        }
        /* Else case-insensitive alpha sort */
        const ta = a.rows[0].cells[colnum].textContent.toUpperCase();
        const tb = b.rows[0].cells[colnum].textContent.toUpperCase();
        if (ta > tb)
          return 1 * sortdirection;
        if (ta < tb)
          return -1 * sortdirection;
        return 0;
      }).forEach(tb => table.appendChild(tb));

      table.querySelectorAll('a.sortheader').forEach((a) => {
        a.dataset.sorted = (a == e.target) ? sortdirection : '';
      });

      /* Need this to update the sequence number properly */
      filter_sessions();
    });
  });

  document.querySelectorAll('td.flt-votes select').forEach((sel) => {
    sel.addEventListener('change', (e) => {
      castVote(e.target.closest('tr.sessionrow').dataset.sid);
    });
  });
  document.querySelectorAll('td.fld-status').forEach((td) => {
    td.addEventListener('click', (e) => {
      changeStatus(e.target.closest('tr.sessionrow').dataset.sid);
    });
  });

  document.querySelectorAll('a.selup').forEach((a) => {
    a.title = 'Click to mark all entries from this row and up, based on the current view';
    a.addEventListener('click', (e) => {
      const tbody = e.target.closest('tbody');
      for (let current = tbody ; current != null ; current = current.previousElementSibling) {
        const cb = current.querySelector('tr td.flt-seq input[type="checkbox"]');
        if (cb && current.querySelector('tr.sessionrow').style.display != 'none') {
          cb.checked = true;
        }
      };
    });
  });
  document.querySelectorAll('a.seldown').forEach((a) => {
    a.title = 'Click to mark all entries from this row and down, based on the current view';
    a.addEventListener('click', (e) => {
      const tbody = e.target.closest('tbody');
      for (let current = tbody ; current != null ; current = current.nextElementSibling) {
        const cb = current.querySelector('tr td.flt-seq input[type="checkbox"]');
        if (cb && current.querySelector('tr.sessionrow').style.display != 'none') {
          cb.checked = true;
        }
      };
    });
  });

  const dlgStatus = document.getElementById('dlgStatus');
  dlgStatus.querySelectorAll('button').forEach((b) => {
    b.addEventListener("click", (e) => {
      dlgStatus.close(e.target.dataset.statusid);
    });
  });
  dlgStatus.addEventListener("close", () => {
    if (dlgStatus.returnValue) {
      doUpdateStatus(dlgStatus.dataset.sid, dlgStatus.returnValue);
    }
  });

  const dlgComment = document.getElementById('dlgComment');
  dlgComment.querySelector('button').addEventListener('click', (e) => {
    dlgComment.close('save');
  });
  dlgComment.addEventListener("close", () => {
    if (dlgComment.returnValue == 'save') {
      doSaveComment(dlgComment.dataset.sid);
    }
  });
  document.getElementById('dlgCommentText').addEventListener('keyup', (e) => {
    if (e.keyCode == 13) {
      document.querySelector('dialog#dlgComment button').click();
    }
  });
  document.querySelectorAll('td.flt-cmt a.btn').forEach((a) => {
    a.addEventListener('click', (e) => {
      editComment(e.target.closest('tr.sessionrow').dataset.sid);
    });
  });

  if (document.getElementById('btnClearCheckboxes')) {
    document.getElementById('btnClearCheckboxes').addEventListener('click', (e) => {
      document.querySelectorAll('td.flt-seq input[type="checkbox"]').forEach((c) => {
        c.checked = false;
      });
    });
  }

  if (document.getElementById('btnBulkStatus')) {
    document.getElementById('btnBulkStatus').addEventListener('click', (e) => {
      const idlist = [...document.querySelectorAll('tr.sessionrow:has(td.flt-seq input[type="checkbox"]:checked)')].map((e) => e.dataset.sid);
      const statuslist = new Set([...document.querySelectorAll('tr.sessionrow:has(td.flt-seq input[type="checkbox"]:checked)')].map((e) => e.dataset.status));
      const transitions = [...statuslist].map((s) => new Set(Object.keys(valid_status_transitions[s])));

      const valid = transitions.reduce((acc, currval) => {
        return acc.intersection(currval);
      });

      if (!valid.size) {
        alert('There are no valid status transitions for all the selected sessions.');
        return;
      }

      const dialog = document.getElementById('dlgStatus');
      dialog.dataset.sid = idlist;
      dialog.getElementsByTagName('h3')[0].innerText = "Bulk change status for ids " + idlist;;
      const buttonDiv = dialog.getElementsByTagName('div')[0];
      buttonDiv.querySelectorAll('button').forEach((btn) => {
        btn.style.display = (valid.has(btn.dataset.statusid)) ? "inline-block": "none";
      });

      dialog.showModal();
    });
  }

  filter_sessions();
});

function setAjaxStatus(str, iserror) {
  const el = document.getElementById('ajaxStatus');
  el.classList.add(iserror ? 'alert-danger' : 'alert-success');
  el.classList.remove(iserror ? 'alert-success' : 'alert-danger');
  el.innerText = str;
  el.style.display = 'block';
  setInterval(() => {
    el.style.display = 'none';
  }, 2000);
}

function filter_sessions() {
  /* Get all our statuses */
  const statuses = [...document.querySelectorAll('input[type=checkbox].filtercheck_status:checked')].map((cb) => parseInt(cb.id.replace('st_', '')));
  const tracks = [...document.querySelectorAll('input[type=checkbox].filtercheck_track:checked')].map((cb) => parseInt(cb.id.replace('t_', '')));
  const tags = [...document.querySelectorAll('input[type=checkbox].filtercheck_tag:checked')].map((cb) => parseInt(cb.id.replace('tg_', '')));
  const votedlimit = document.querySelector('input[type=checkbox]#vt_1:checked');

  let seq = 1;
  /* Recalculate visibility and sequence for all sessions */
  [...document.querySelectorAll('table#votetable tr.sessionrow')].forEach((row) => {
    /* Default is everything is visible, and then we remove */
    let visible = true;

    if (!statuses.includes(parseInt(row.dataset.status))) {
      visible = false;
    }

    if (!tracks.includes(parseInt(row.dataset.track))) {
      visible = false;
    }

    if (document.querySelector('input.filtercheck_tag')) {
      if (row.dataset.tags) {
        /* If *any* of the specified tags exist we're ok */
        let found = false;
        row.dataset.tags.split(",").map(t => parseInt(t)).forEach(t => {
          if (tags.includes(t)) {
            found = true;
          }
        });
        if (!found) {
          visible = false;
        }
      } else {
        if (!tags.includes(0)) {
          visible = false;
        }
      }
    }

    if (votedlimit && row.querySelector('td[data-voted="yes"]')) {
      visible = false;
    }

    row.style.display = visible ? "table-row" : "none";
    document.getElementById('detailsrow_' + row.dataset.sid).style.display = visible ? "" : "none";

    if (visible) {
      row.querySelector('td div.seq').innerText = seq;
      seq += 1;
    } else {
      row.querySelector('td div.seq').innerText = '';
    }
  });
}

function getFormData(obj) {
  let fd = new FormData();
  Object.entries(obj).forEach(([k, v]) => {
    fd.append(k, v);
  });
  return fd;
}

async function doUpdateStatus(id, statusval) {
  if (!statusval) return;

  const response = await fetch('changestatus/', {
    'method': 'POST',
    'body': getFormData({
      'csrfmiddlewaretoken': document.getElementsByTagName('body')[0].dataset.csrftok,
      'sessionid': id,
      'newstatus': statusval,
    }),
    'credentials': 'same-origin',
  });
  if (response.ok) {
    const j = await response.json();

    id.split(',').forEach((i) => {
      const targetRow = document.querySelector('tr.sessionrow[data-sid="' + i + '"]');
      const targetFld = targetRow.querySelector('td.fld-status');
      targetRow.dataset.status = statusval;
      targetFld.getElementsByTagName('a')[0].text = j.newstatus;
      targetFld.style.backgroundColor = j.statechanged[i] ? 'yellow' : 'white';
    });

    document.getElementById('pendingNotificationsButton').style.display = j.pending ? 'inline-block': 'none';
    setAjaxStatus('Changed status to ' + j.newstatus, false);
  }
  else {
    if (response.status >= 400 && response.status < 500) {
      response.text().then(function (t) {
        setAjaxStatus('Error: ' + t, true);
      });
    } else {
      setAjaxStatus('Error: ' + response.statusText, true);
    }
  }
  return;
}

function changeStatus(id) {
  const currentstatus = document.querySelector('tr.sessionrow[data-sid="' + id + '"]').dataset.status;
  const dialog = document.getElementById('dlgStatus');
  dialog.dataset.sid = id;
  dialog.getElementsByTagName('h3')[0].innerText = "Change status for id " + id;
  const buttonDiv = dialog.getElementsByTagName('div')[0];
  buttonDiv.querySelectorAll('button').forEach((btn) => {
    btn.style.display = (btn.dataset.statusid in valid_status_transitions[currentstatus]) ? "inline-block": "none";
  });

  dialog.showModal();
}

async function castVote(sessionid) {
  const row = document.querySelector('tr.sessionrow[data-sid="' + sessionid + '"]');
  const td = row.querySelector('td.flt-votes:has(select)');
  const s = td.getElementsByTagName('select')[0];
  const avgbox = row.querySelector('td.avgbox');

  const response = await fetch('vote/', {
    'method': 'POST',
    'body': getFormData({
      'csrfmiddlewaretoken': document.getElementsByTagName('body')[0].dataset.csrftok,
      'sessionid': sessionid,
      'vote': s.value,
    }),
    'credentials': 'same-origin',
  });
  if (response.ok) {
    td.dataset.voted = (s.value == 0)?"no":"yes";
    response.text().then(function (t) {
      avgbox.innerText = t;
    });
  } else {
    alert('AJAX call failed');
  }
}

async function doSaveComment(sessionid) {
  const dialog = document.getElementById('dlgComment');
  const row = document.querySelector('tr.sessionrow[data-sid="' + sessionid + '"]');
  const cspan = row.querySelector('li.owncomment span.comment');
  const txt = document.getElementById('dlgCommentText').value;

  if (txt != cspan.innerText) {
    const response = await fetch('comment/', {
      'method': 'POST',
      'body': getFormData({
        'csrfmiddlewaretoken': document.getElementsByTagName('body')[0].dataset.csrftok,
        'sessionid': sessionid,
        'comment': txt,
      }),
      'credentials': 'same-origin',
    });
    if (response.ok) {
      response.text().then(function (t) {
        cspan.innerText = t;
        row.querySelector('li.owncomment').style.display = (t == '') ? 'none' : 'block';
      });
    }
    else {
      alert('AJAX call failed');
    }
  }
}

function editComment(sessionid) {
  const dialog = document.getElementById('dlgComment');
  const row = document.querySelector('tr.sessionrow[data-sid="' + sessionid + '"]');
  const old = row.querySelector('li.owncomment span.comment').innerText;

  document.getElementById('dlgCommentText').value = old;
  dialog.dataset.sid = sessionid;

  dialog.showModal();
}
