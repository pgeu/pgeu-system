/* Global websocket reference and other variables */
let ws = null;
let noretry = false;
let manuallydisconnected = false;
let highestseen = 0;
let lastdate = null;
let isadmin = false;
let selfuser = -1;
let userlist = {};

function dofocus() {
    document.getElementById('meeting-input-text').focus();
}

function refresh_user_list() {
    const e = document.querySelector('div.meeting-content ul.meeting-attendee-list');
    const newul = e.cloneNode(false);

    if (Object.keys(userlist).length <= 0) {
        /* No users, so clean out the list */
        e.parentNode.replaceChild(newul, e);
        return;
    }

    Object.keys(userlist).sort((a, b) => {
        /* Sort the keys in the order of the name of the user for that key */
        return ((userlist[a]['name'] < userlist[b]['name']) ? -1 : ((userlist[a]['name'] > userlist[b]['name']) ? 1 : 0));
    }).forEach(id => {
        const v = userlist[id];
        const li = document.createElement('li');
        li.className = 'user-list-entry user-color-' + v['color'];
        li.appendChild(document.createTextNode(v['name']));
        if (isadmin) {
            let check = document.createElement('div');
            check.innerText = "\u2713";
            check.classList.add('admin-user-checkmark');
            check.title = v['name'] + ' has voted in the current poll.';
            li.appendChild(check);

            if (v['id'] != selfuser) {
                let btn = document.createElement('div');
                btn.innerText = "\u00D7";
                btn.classList.add('admin-user-button');
                btn.title = 'Disconnect ' + v['name'];
                btn.addEventListener('click', adminUserDisconnectClick);
                li.appendChild(btn);
            }

            li.dataset.uid = v['id'];
            li.dataset.name = v['name'];
        }
        newul.appendChild(li);
    });
    e.parentNode.replaceChild(newul, e);
}

function replace_user_list(users) {
    userlist = users.reduce((a, c) => {
        a[c['id']] = c;
        return a;
    }, {});
    refresh_user_list();
}

function add_user_to_list(user) {
    userlist[user.id] = user;
    refresh_user_list();
}

function remove_user_from_list(user) {
    delete(userlist[user.id]);
    refresh_user_list();
}

function status(level, msg) {
    const e = document.getElementById('meeting-status');

    if (e.className != 'status-' + level)
        e.className = 'status-' + level;
    if (e.innerText != msg)
        e.innerText = msg;
}

function status_connected() {
    status('normal', 'Connected');
}

function handle_incoming_message(data, scrollifbottom) {
    const wrap = document.querySelector('div.meeting-chat');
    const e = wrap.querySelector('table');

    /*
     * If scrollifbottom is true *and* we are currently scrolled to the bottom, then force-scroll
     * so the new row is visible for flow.
     */
    const doscroll = scrollifbottom &&
          (wrap.scrollHeight - Math.abs(wrap.scrollTop) === wrap.clientHeight);


    if (data.date !== lastdate)  {
        lastdate = data.date;
        const row = document.createElement('tr');
        row.className = 'meeting-row-date';
        const col = document.createElement('td');
        col.colSpan = 3;
        col.appendChild(document.createTextNode('Date changed to ' + data.date));
        row.appendChild(col);
        e.appendChild(row);
    }

    /* Prepare the content row */
    const row = document.createElement('tr');
    const timecol = document.createElement('td');
    const namecol = document.createElement('td');
    const txtcol = document.createElement('td');

    row.classList.add('meeting-row');
    timecol.className = 'meeting-col-time';
    namecol.className = 'meeting-col-name user-color-' + data.color;
    txtcol.className = 'meeting-col-text';

    timecol.appendChild(document.createTextNode(data.time));
    if (data.fromname)
        /* Can be NULL if it's a system message */
        namecol.appendChild(document.createTextNode(data.fromname));
    else
        row.classList.add('meeting-row-sys');
    txtcol.appendChild(document.createTextNode(data.message));

    row.appendChild(timecol);
    row.appendChild(namecol);
    row.appendChild(txtcol);
    e.appendChild(row);

    if (data.id > highestseen)
        highestseen = data.id;

    if (doscroll) {
        row.scrollIntoView();
    }

    return row;
}

function refresh_poll_status(poll, meetingopen) {
    if (!meetingopen) {
        /* If meeting isn't open, don't touch anything */
        return;
    }

    if (!poll) {
        /* Poll is closed, so just hide it */
        document.getElementById('meeting-poll').style.display = 'none';
        if (document.getElementById('controls-new-poll')) {
            document.getElementById('controls-new-poll').style.display = 'block';
            document.getElementById('controls-abort-poll').style.display = 'none';
        }
        if (isadmin) {
            /* Remove the checkmark from all users */
            document.querySelectorAll('ul.meeting-attendee-list li.user-list-entry div.admin-user-checkmark').forEach(e => {
                e.style.display = 'none';
            });
        }
        return;
    }

    /* If the poll is hidden this was the first refresh. Some data only needs to be updated then */
    const first = document.getElementById('meeting-poll').style.display != 'block';
    if (document.getElementById('controls-new-poll')) {
        document.getElementById('controls-new-poll').style.display = 'none';
        document.getElementById('controls-abort-poll').style.display = 'block';
    }

    const meter = document.getElementById('poll-meter');

    if (first) {
        /* Else populate the poll with information */
        document.getElementById('poll-question').innerText = poll.question;
        for (let i = 0 ; i < poll.answers.length; i++) {
            const e = document.getElementById('poll-button-' + i);
            e.innerText = poll.answers[i];
            e.style.display = '';
        }
        for (let i = poll.answers.length; i < 5; i++) {
            document.getElementById('poll-button-' + i).style.display = 'none';
        }

        /* Set up the meter empty */
        meter.value = 0;
        meter.max = document.querySelectorAll('div.meeting-content ul.meeting-attendee-list li').length;

        /* Ensure all buttons are available */
        document.querySelectorAll('button.poll-button').forEach(bb => {
            bb.disabled = false;
        });

        /* Show the poll */
        document.getElementById('meeting-poll').style.display = 'block';
    }

    /*
     * Which users have voted?
     */
    if (isadmin) {
        document.querySelectorAll('ul.meeting-attendee-list li.user-list-entry').forEach(e => {
            const div = e.querySelector('div.admin-user-checkmark');
            if (poll.voted.includes(parseInt(e.dataset.uid))) {
                div.style.display = 'inline-block';
            }
            else {
                div.style.display = 'none';
            }
        });
    }

    /* Update statistics on every update */
    meter.value = poll.tally.reduce((a, b) => a + b)
    meter.title = `${meter.value} of ${meter.max} votes have been cast`;
}

function refresh_status(status) {
    if (!document.getElementById('meeting-control'))
        return;

    if (!status.isopen) {
        document.getElementById('controls-closed').style.display = 'block';
        document.querySelectorAll('.controls-in-open').forEach(e => {
            e.style.display = 'none';
        });
    }
    else if (!status.isfinished) {
        document.getElementById('controls-closed').style.display = 'none';
        document.querySelectorAll('.controls-in-open').forEach(e => {
            e.style.display = 'block';
        });
    }
    else {
        document.getElementById('controls-closed').style.display = 'none';
        document.querySelectorAll('.controls-in-open').forEach(e => {
            e.style.display = 'none';
        });
        document.getElementById('controls-finished').style.display = 'block';
    }
    document.getElementById('btn-open-meeting').innerText = status.isfinished ? "Re-open meeting" : "Open meeting";

    refresh_poll_status(status.isopen);
}

function setup_websocket() {
    const e = document.getElementsByClassName('meeting-content')[0];
    const key = e.dataset.key;
    const meetingid = e.dataset.meetingid;
    const wsbaseurl = e.dataset.wsbaseurl;
    selfuser = parseInt(e.dataset.userid);

    if (noretry)
        return;

    status('warning', 'Connecting...');

    // ws is a global variable
    ws = new WebSocket(wsbaseurl + '/' + meetingid + '/' + key + '/' + highestseen);
    ws.onopen = function(event) {
        status('warning', 'Waiting for response...');
        document.getElementById('meeting-disconnect-button').style.display = 'inline-block';
    };
    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type == 'message') {
            handle_incoming_message(data.data, true);
            status_connected();
        }
        else if (data.type == 'messages') {
            /* Multiple messages received at once. Used so we can make one big DOM update */
            let row = null;
            data.data.forEach(d => {
                row = handle_incoming_message(d, false);
            });
            if (row)
                row.scrollIntoView();
            status_connected();
        }
        else if (data.type == 'users') {
            replace_user_list(data.data.users);
            status_connected();
        }
        else if (data.type == 'adduser') {
            add_user_to_list(data.data);
        }
        else if (data.type == 'removeuser') {
            remove_user_from_list(data.data);
        }
        else if (data.type == 'poll') {
            refresh_poll_status(data.data, true);
            status_connected();
        }
        else if (data.type == 'status') {
            refresh_status(data.data);
            status_connected();
        }
        else if (data.type == 'error') {
            status('error', data.msg);
        }
        else if (data.type == 'disconnect') {
            handle_incoming_message(data.data, true);
            status('error', 'Disconnected');
            noretry = true;
        }
        else {
            status('warning', 'Unknown event received');
            console.log("Unknown event " + data.type + " received.")
        }
    }
    ws.onclose = function(event) {
        if (event.code > 400 && event.code != 1006 && !manuallydisconnected) {
            status('error', 'Failed to connect to server');
            console.log("Permanent error from websocket (" + event.code + "), disabling autoretry");
            noretry = true;
        }

        document.getElementById('meeting-disconnect-button').style.display = 'none';
        if (!noretry)
            status('error', 'Websocket disconnected.');
        setTimeout(function() {
            setup_websocket();
        }, 2000);
    }
}

function doSendText() {
    const sendtext = document.getElementById('meeting-input-text');
    if (sendtext.value && ws) {
        ws.send(JSON.stringify({
            'type': 'message',
            'message': sendtext.value.trim(),
        }));
        sendtext.value = '';

        /* Remove the header on mobile, to mazimize space */
        document.getElementsByClassName('meeting-header')[0].classList.add('slideuponsmall');
    }

    dofocus();
}

function adminUserDisconnectClick() {
    const userel = event.target.parentElement;
    const name = userel.dataset.name;

    if (confirm('Are you sure you want to disconnect the user ' + name + '?')) {
        const canrejoin = confirm('Should ' + name + ' be allowed to re-join the meeting?');

        ws.send(JSON.stringify({
            'type': 'kick',
            'user': parseInt(userel.dataset.uid),
            'canrejoin': canrejoin,
        }));
    }
}

function setup_meeting() {
    document.getElementById('meeting-send-button').addEventListener('click', doSendText);
    document.getElementById('meeting-input-text').addEventListener('keydown', event => {
        if (event.keyCode == 13) {
            doSendText();
        }
    });
    document.getElementById('meeting-disconnect-button').addEventListener('click', event => {
        if (ws) {
            noretry = true;
            manuallydisconnected = true;
            ws.close();
            status('error', 'Disconnected. Reload page to reconnect.');
        }
    });
    document.getElementById('cb_usercolors').addEventListener('click', event => {
        const e = document.getElementById('cb_usercolors');
        if (e.checked) {
            document.body.classList.add('usercolors');
        }
        else {
            document.body.classList.remove('usercolors');
        }
    });

    document.querySelectorAll('button.poll-button').forEach(b => {
        b.addEventListener('click', e => {
            ws.send(JSON.stringify({
                'type': 'vote',
                'question': document.getElementById('poll-question').innerText, /* Just to make sure we're voting on the correct one */
                'vote': parseInt(b.id.split('-').pop()),
            }));
            /* Enable all other buttons and disable this one */
            document.querySelectorAll('button.poll-button').forEach(bb => {
                bb.disabled = false;
            });
            b.disabled = true;
        });
    });

    if (document.getElementById('btn-open-meeting')) {
        /* User has the admin html */
        isadmin = true;

        document.getElementById('btn-open-meeting').addEventListener('click', function() {
            if (confirm("Are you sure you want to open this meeting?")) {
                ws.send(JSON.stringify({
                    'type': 'open'
                }));
            }
        });
        document.getElementById('btn-finish-meeting').addEventListener('click', function() {
            if (confirm("Are you sure you want to finish this meeting? There is no going back!")) {
                ws.send(JSON.stringify({
                    'type': 'finish'
                }));
            }
        });
        document.getElementById('btn-abort-poll').addEventListener('click', function() {
            if (confirm("Are you sure you want to abort this poll and throw away all results?")) {
                ws.send(JSON.stringify({
                    'type': 'abortpoll'
                }));
            }
        });
        document.getElementById('btn-new-poll').addEventListener('click', function() {
            const question = document.getElementById('new_poll_question').value;
            if (question.length  < 1) {
                alert('Must specify a question!');
                return;
            }

            let answers = [];
            for (let i = 0; i < 5; i++) {
                const v = document.getElementById('new_poll_' + i).value;
                if (v)
                    answers.push(v);
            }
            if (answers.length < 2) {
                alert('Must provide at least two options');
                return;
            }

            const minutes = parseInt(document.getElementById('poll_time').value);
            if (minutes < 0) {
                alert('Must specify a time above zero.');
                return;
            }
            if (minutes > 10) {
                alert('Time over 10 minutes prevented.');
            }

            if (!confirm("Are you sure you're ready to send this poll?")) {
                return;
            }

            ws.send(JSON.stringify({
                'type': 'newpoll',
                'question': question,
                'answers': answers,
                'minutes': minutes,
            }));

            /* Clean out and prepare for the next one */
            document.getElementById('new_poll_question').value = '';
            document.querySelectorAll('#controls-new-poll input[type=text]').forEach(e => {
                e.value = '';
            });
            document.getElementById('poll_time').value = 5;
        });
    }

    dofocus();

    setup_websocket();
}

setup_meeting();
