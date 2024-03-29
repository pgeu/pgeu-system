from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect, Http404
from django.contrib.auth.decorators import login_required

from postgresqleu.util.time import today_global
from postgresqleu.util.db import exec_to_dict
from .models import Election, Member, Candidate, Vote
from .forms import VoteForm
from datetime import timedelta


def home(request):
    elections = Election.objects.filter(isactive=True).order_by('startdate')
    open_elections = [e for e in elections if e.startdate <= today_global() and e.enddate >= today_global()]
    past_elections = [e for e in elections if e.startdate < today_global() and e.enddate < today_global()]
    upcoming_elections = [e for e in elections if e.startdate > today_global()]

    return render(request, 'elections/home.html', {
        'open': open_elections,
        'past': past_elections,
        'upcoming': upcoming_elections,
    })


def election(request, electionid):
    election = get_object_or_404(Election, pk=electionid)
    if not election.isactive:
        raise Http404("This election is not active")

    if election.startdate > today_global():
        raise Http404("This election has not started yet")

    if election.enddate < today_global():
        # Election is closed, consider publishing the results
        if not election.resultspublic:
            # If user is an admin, show anyway, otherwise throw an error
            if not request.user.is_superuser:
                raise Http404("The results for this election aren't published yet.")

        # Ok, so we do have the results. Use a custom query to make sure we get decently formatted data
        # and no client-side ORM aggregation
        scores = exec_to_dict("""WITH t AS (
 SELECT c.name, sum(v.score) AS score
 FROM elections_candidate c
 INNER JOIN elections_vote v ON c.id=v.candidate_id
 WHERE v.election_id=%(election)s AND c.election_id=%(election)s
 GROUP BY c.id
 ), tt AS (
SELECT
 name, score,
 rank() OVER (ORDER BY score DESC) AS rank,
 count(1) OVER (PARTITION BY score) AS numingroup
 FROM t
)
SELECT name, score,
 %(barwidth)s * score / first_value(score) OVER (ORDER BY score DESC) AS width,
 CASE WHEN rank+numingroup-2 < %(slots)s THEN 'Elected'
      WHEN rank+numingroup-2 = %(slots)s AND numingroup>1 THEN 'Tied'
      ELSE 'Lost' END AS elected
FROM tt
ORDER BY 2 DESC""", {
            'election': election.pk,
            'slots': election.slots,
            'barwidth': 300,
        })
        if len(scores) == 0:
            raise Http404('No results found for this election')

        return render(request, 'elections/results.html', {
            'election': election,
            'scores': scores,
        })

    if len(election.candidate_set.all()) <= 0:
        raise Http404("This election has no candidates!")

    # Otherwise, we show up the form. This part requires login
    if not request.user.is_authenticated:
        return HttpResponseRedirect("/login/?next=%s" % request.path)

    try:
        member = Member.objects.get(user=request.user)

        # Make sure member has paid
        if not member.paiduntil:
            return render(request, 'elections/mustbemember.html', {})

        # Make sure that the membership hasn't expired
        if member.paiduntil < today_global():
            return render(request, 'elections/mustbemember.html', {})

        # Verify that the user has been a member for at least 28 days.
        if member.membersince > election.startdate - timedelta(days=28):
            return render(request, 'elections/memberfourweeks.html', {
                'membersince': member.membersince,
                'mustregbefore': election.startdate - timedelta(days=28),
                'election': election,
            })

    except Member.DoesNotExist:
        return render(request, 'elections/mustbemember.html', {})

    if request.method == "POST":
        form = VoteForm(election, member, data=request.POST)
        if form.is_valid():
            # Save the form
            form.save()
    else:
        # Not a POST, so generate an empty form
        form = VoteForm(election, member)

    return render(request, 'elections/form.html', {
        'form': form,
        'election': election,
    })


def candidate(request, election, candidate):
    candidate = get_object_or_404(Candidate, election=election, pk=candidate)

    return render(request, 'elections/candidate.html', {
        'candidate': candidate,
    })


@login_required
def ownvotes(request, electionid):
    election = get_object_or_404(Election, pk=electionid)
    if not election.isactive:
        raise Http404("This election is not active")

    if election.enddate >= today_global():
        raise Http404("This election has not ended yet")

    member = get_object_or_404(Member, user=request.user)

    votes = Vote.objects.select_related().filter(voter=member, election=election).order_by('-score')

    return render(request, 'elections/ownvotes.html', {
        'election': election,
        'votes': votes,
    })
