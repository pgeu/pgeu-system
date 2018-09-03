{%load markup%}
<dl class="eventlist">
{%for event in events%}
<dt><h5>{%if event.confurl%}<a href="{{event.confurl}}">{{event.conferencename}}</a>{%else%}{{event.conferencename}}{%endif%}</h5></dt>
<dd>
<p class='lead'>
  <span class="nobr"><i class="fa fa-calendar-o"></i> {{event.conferencedatestr}}</span>
&nbsp;&nbsp;
  <span class="nobr"><i class="fa fa-map-pin"></i> {{event.location}}</span>
</p>
{%if event.promotext%}
{{event.promotext|markdown}}
{%endif%}
<a class="btn btn-primary btn-sm" href="{{event.confurl}}">View website</a>
{%if event.active and what == "reg"%}<a class="btn btn-primary btn-sm" href="/events/{{event.urlname}}/register/">Register</a>{%endif%}
{%if event.callforpapersopen and what == "cfp"%}<a class="btn btn-primary btn-sm" href="/events/{{event.urlname}}/callforpapers/">Submit presentation</a>{%endif%}
{%if event.callforsponsorsopen and what == "cfs"%}<a class="btn btn-primary btn-sm" href="/events/sponsor/signup/{{event.urlname}}/">Sign up</a>{%endif%}
</dd>
{%endfor%}
    </dl>
