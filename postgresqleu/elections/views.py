from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect, Http404
from django.contrib.auth.decorators import login_required
from django.db import connection

from models import Election, Member, Candidate, Vote
from forms import VoteForm
from datetime import date, timedelta

def home(request):
    elections = Election.objects.filter(isopen=True).order_by('startdate')
    open_elections = [e for e in elections if e.startdate<=date.today() and e.enddate>=date.today()]
    past_elections = [e for e in elections if e.startdate<date.today() and e.enddate<date.today()]
    upcoming_elections = [e for e in elections if e.startdate>date.today()]

    return render(request, 'elections/home.html', {
        'open': open_elections,
        'past': past_elections,
        'upcoming': upcoming_elections,
    })

def election(request, electionid):
    election = get_object_or_404(Election, pk=electionid)
    if not election.isopen:
        raise Http404("This election is not open (yet)")

    if election.startdate > date.today():
        raise Http404("This election has not started yet")

    if election.enddate < date.today():
        # Election is closed, consider publishing the results
        if not election.resultspublic:
            # If user is an admin, show anyway, otherwise throw an error
            if not request.user.is_superuser:
                raise Http404("The results for this election aren't published yet.")

        # Ok, so we do have the results. Use a custom query to make sure we get decently formatted data
        # and no client-side ORM aggregation
        curs = connection.cursor()
        curs.execute("SELECT c.name, sum(v.score) AS score FROM elections_candidate c INNER JOIN elections_vote v ON c.id=v.candidate_id WHERE v.election_id=%(election)s AND c.election_id=%(election)s GROUP BY c.name ORDER BY 2 DESC", {
            'election': election.pk,
        })
        res = curs.fetchall()
        if len(res) == 0:
            raise Http404('No results found for this election')

        return render(request, 'elections/results.html', {
            'election': election,
            'topscore': res[0][1],
            'scores': [{'name': r[0], 'score': r[1], 'width': 300*r[1]/res[0][1]} for r in res],
        })

    if len(election.candidate_set.all()) <= 0:
        raise Http404("This election has no candidates!")

    # Otherwise, we show up the form. This part requires login
    if not request.user.is_authenticated():
        return HttpResponseRedirect("/login/?next=%s" % request.path)

    try:
        member = Member.objects.get(user=request.user)

        # Make sure member has paid
        if not member.paiduntil:
            return render(request, 'elections/mustbemember.html', {})

        # Make sure that the membership hasn't expired
        if member.paiduntil < date.today():
            return render(request, 'elections/mustbemember.html', {})

        # Verify that the user has been a member for at least 28 days.
        if member.membersince > election.startdate - timedelta(days=28):
            return render(request, 'elections/memberfourweeks.html', {
                'registered_at': member.paiduntil - timedelta(days=365),
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
    if not election.isopen:
        raise Http404("This election is not open (yet)")

    if election.enddate >= date.today():
        raise Http404("This election has not ended yet")

    member = get_object_or_404(Member, user=request.user)

    votes = Vote.objects.select_related().filter(voter=member, election=election).order_by('-score')

    return render(request, 'elections/ownvotes.html', {
        'election': election,
        'votes': votes,
    })
