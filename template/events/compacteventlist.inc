<dl class="eventlist">
{%for event in events%}
<dt><h5>{%if event.confurl%}<a href="{{event.confurl}}">{{event.conferencename}}</a>{%else%}{{event.conferencename}}{%endif%}</h5></dt>
<dd>
  <span class="nobr"><i class="fa fa-calendar-o"></i> {{event.conferencedatestr}}</span><br/>
  <span class="nobr"><i class="fa fa-map-pin"></i> {{event.location}}</span>
</dd>
{%endfor%}
    </dl>
