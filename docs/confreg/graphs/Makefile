all: talk_states.svg regular_reg.svg waitlist.svg sponsorsignup.svg

%.svg: %.dot
	dot -Tsvg $< > $@
