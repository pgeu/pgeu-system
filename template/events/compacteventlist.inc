{%for event in events%}
{%if forloop.first and not splityears%}<dl class="eventlist">{%endif%}
{%if splityears%}{%ifchanged event.startdate|date:"Y"%}
{%if not forloop.first%}</dl>{%endif%}
<h2>{{event.startdate|date:"Y"}}</h2>
<dl class="eventlist">
{%endifchanged%}{%endif%}
<dt><h5>{%if event.confurl%}<a href="{{event.confurl}}">{{event.conferencename}}</a>{%else%}{{event.conferencename}}{%endif%}</h5></dt>
<dd>
  <span class="nobr"><i class="fa fa-calendar-o"></i> {{event.conferencedatestr}}</span><br/>
  <span class="nobr"><i class="fa fa-map-pin"></i> {{event.location}}</span>
</dd>
{%endfor%}
</dl>
