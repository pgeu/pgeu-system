<h2>{{title}} events in {{series}}</h2>
<ul>
{%for e in l%}
<li>{%if  e.confurl%}<a href="{{e.confurl}}">{{e.conferencename}}</a>{%else%}{{e.conferencename}}{%endif%}</li>
{%endfor%}
</ul>