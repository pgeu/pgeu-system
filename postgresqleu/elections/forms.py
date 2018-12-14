from django import forms
from django.forms.utils import ErrorList
from django.db import transaction

from models import Vote
from postgresqleu.membership.models import MemberLog

from datetime import datetime


class VoteForm(forms.Form):
    def __init__(self, election, member, *args, **kwargs):
        super(VoteForm, self).__init__(*args, **kwargs)

        self.saved_and_modified = False

        self.election = election
        self.member = member

        self.candidates = election.candidate_set.all().order_by('name')
        self.votes = Vote.objects.filter(election=election, voter=member)

        votemap = {}
        for vote in self.votes:
            votemap[vote.candidate_id] = vote.score

        dropdown = [(x, self._votestring(x)) for x in range(1, len(self.candidates) + 1)]
        dropdown.insert(0, (-1, '** Please rate this candidate'))

        # Dynamically add a dropdown field for each candidate
        for candidate in self.candidates:
            self.fields['cand%i' % candidate.id] = forms.ChoiceField(choices=dropdown,
                                                                     label=candidate.name,
                                                                     required=True,
                                                                     help_text=candidate.id,
                                                                     initial=votemap.has_key(candidate.id) and votemap[candidate.id] or -1)

    def _votestring(self, x):
        if x == 1:
            return "1 - Least favourite"
        if x == len(self.candidates):
            return "%s - Favourite" % len(self.candidates)
        return "%s" % x

    def clean(self):
        # First, make sure all existing fields are actually filled out
        for (k, v) in self.cleaned_data.items():
            if k.startswith('cand'):
                if v == "-1":
                    self._errors[k] = ErrorList(["You need to select a score for this candidate!"])
            else:
                raise Exception("Invalid field name found: %s" % k)

        # Second, make sure the fields match the candidates
        fields = self.cleaned_data.copy()
        for candidate in self.candidates:
            if fields.has_key("cand%i" % candidate.id):
                del fields["cand%i" % candidate.id]
            else:
                raise Exception("Data for candidate %i is missing" % candidate.id)

        if len(fields) > 0:
            raise Exception("Data for candidate not standing for election found!")

        # Finally, verify that all options have been found, and none have been duplicated
        options = range(1, len(self.candidates) + 1)
        for k, v in self.cleaned_data.items():
            if int(v) in options:
                # First use is ok. Take it out of the list, so next attempt generates error
                del options[options.index(int(v))]
            else:
                # Not in the list means it was already used! Bad user!
                if not self._errors.has_key(k):
                    # Only add this error in case the other error hasn't already fired
                    self._errors[k] = ErrorList(["This score has already been given to another candidate"])

        if len(options) != 0:
            raise forms.ValidationError("One or more scores was not properly assigned!")

        return self.cleaned_data

    @transaction.atomic
    def save(self):
        # Let's see if the old votes are here
        if len(self.votes) == 0:
            # This is completely new, let's create votes for him
            for k, v in self.cleaned_data.items():
                id = int(k[4:])
                Vote(election=self.election, voter=self.member, candidate_id=id, score=v).save()
            self.votes = Vote.objects.filter(election=self.election, voter=self.member)
            MemberLog(member=self.member, timestamp=datetime.now(),
                      message="Voted in election '%s'" % self.election.name).save()
            self.saved_and_modified = True
        elif len(self.votes) == len(self.candidates):
            # Ok, we have one vote for each candidate already, so modify them as necessary
            changedany = False
            for vote in self.votes:
                score = int(self.cleaned_data['cand%i' % vote.candidate_id])
                if vote.score != score:
                    vote.score = score
                    vote.save()
                    changedany = True

            if changedany:
                MemberLog(member=self.member, timestamp=datetime.now(),
                          message="Changed votes in election '%s'" % self.election.name).save()
                self.saved_and_modified = True
        else:
            raise Exception("Invalid number of records found in database, unable to update vote.")
