from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER

################
# Some basic/sample badge types
################
class SimpleSingledayBadge(object):
	def getsize(self):
		return (103*mm, 138*mm)

	def draw(self, base):
		reg = base.reg
		canvas = base.canv

		# Border of the badge itself
		canvas.rect(0,0,base.width, base.height)

		# Blue box that will take the elephant
		base.setFill(33, 139, 181)
		canvas.rect(4*mm, base.ycoord(10, 28), base.width-(2*4*mm), 28*mm, stroke=0, fill=1)

		# PostgreSQL logo in it!
		canvas.drawImage(base.pglogo_white_name,
						 8*mm, base.ycoord(12, 25),
						 25*mm, 25*mm,
						 mask='auto')

		# Now the actual conference information
		base.drawDynamicParagraph("%s\n%s" % (reg.conference.conferencename, reg.conference.location),
								  35*mm, base.ycoord(12, 25), # x=8+25+<misc>
								  base.width-(40*mm), 25*mm,
								  colors.white)

		# Let's get the name info on there
		base.drawDynamicParagraph("%s %s" % (reg.firstname, reg.lastname),
								  8*mm, base.ycoord(50, 10),
								  60*mm, 10*mm,
								  colors.black,
								  bold=True)
		# Company
		base.drawDynamicParagraph(reg.company,
								  8*mm, base.ycoord(60, 8),
								  60*mm, 8*mm,
								  colors.black,
								  maxsize=14)
		if reg.nick or reg.twittername:
			if reg.nick and reg.twittername:
				nickstr = "Nick: %s Twitter: %s" % (reg.nick, reg.twittername)
			else:
				nickstr = reg.nick and "Nick: %s" % reg.nick or "Twitter: %s" % reg.twittername
			base.drawDynamicParagraph(nickstr,
									  8*mm, base.ycoord(70, 8),
									  60*mm, 8*mm,
									  colors.black,
									  maxsize=12)

		# Draw the QR code
		base.drawQR(70*mm, 50*mm)


class Pgconf2013Badge(object):
	def getsize(self):
		return (103*mm, 138*mm)

	def draw(self, base):
		reg = base.reg
		regtype = reg.regtype
		canvas = base.canv

		# Border of the badge itself
		canvas.rect(0,0,base.width, base.height)

		# Blue box that will take the elephant
		base.setFill(33, 139, 181)
		canvas.rect(4*mm, base.ycoord(10, 28), base.width-(2*4*mm), 28*mm, stroke=0, fill=1)

		# PostgreSQL logo in it!
		canvas.drawImage(base.pglogo_white_name,
						 8*mm, base.ycoord(12, 25),
						 25*mm, 25*mm,
						 mask='auto')

		# Now the actual conference information
		base.drawDynamicParagraph("PostgresSQL\nConference Europe\nDublin 2013",
								  35*mm, base.ycoord(12, 25), # x=8+25+<misc>
								  base.width-(40*mm), 25*mm,
								  colors.white)

		# Let's get the name info on there
		base.drawDynamicParagraph("%s %s" % (reg.firstname, reg.lastname),
								  8*mm, base.ycoord(50, 10),
								  60*mm, 10*mm,
								  colors.black,
								  bold=True)
		# Company
		base.drawDynamicParagraph(reg.company,
								  8*mm, base.ycoord(60, 8),
								  60*mm, 8*mm,
								  colors.black,
								  maxsize=14)
		if reg.nick or reg.twittername:
			if reg.nick and reg.twittername:
				nickstr = "Nick: %s\nTwitter: %s" % (reg.nick, reg.twittername)
			else:
				nickstr = reg.nick and "Nick: %s" % reg.nick or "Twitter: %s" % reg.twittername
			base.drawDynamicParagraph(nickstr,
									  8*mm, base.ycoord(70, 14),
									  60*mm, 14*mm,
									  colors.black,
									  maxsize=12)

		# Draw the QR code
		base.drawQR(70*mm, 50*mm)

		# Draw the txt info about wifi etc
		base.drawDynamicParagraph("WLAN password: dublin2013 (SSID: pgconfeu)\nMobile schedule: http://pgconf.eu/m",
								  8*mm, base.ycoord(105, 15),
								  85*mm, 15*mm,
								  colors.black)

		# Draw the type-of-attendee area
		base.setFillTuple(regtype.regclass.colortuple())
		canvas.rect(8*mm, base.ycoord(90, 10), 85*mm, 10*mm, stroke=0, fill=1)
		base.drawDynamicParagraph(regtype.regclass.regclass,
								  8*mm, base.ycoord(90, 10),
								  85*mm, 10*mm,
								  colors.black,
								  alignment=TA_CENTER)

		# Days
		base.setFill(0,0,0)
		regdays = [d.day.strftime('%a') for d in regtype.days.all()]
		availabledays = ['Tue', 'Wed', 'Thu', 'Fri']
		for n in range(0, len(availabledays)):
			dayname = availabledays[n]
			hasday = dayname in regdays
			xstart = 8*mm + 23*mm*n
			canvas.rect(xstart, base.ycoord(120, 10),
						20*mm, 10*mm,
						stroke=1, fill=hasday)
			base.drawDynamicParagraph(dayname,
									  xstart, base.ycoord(120, 10),
									  20*mm, 10*mm,
									  hasday and colors.white or colors.black,
									  maxsize=16,
									  alignment=TA_CENTER,
									  verticalcenter=True)
