all: talk_states.svg regular_reg.svg waitlist.svg

%.svg: %.dot
	dot -Tsvg $< > $@
