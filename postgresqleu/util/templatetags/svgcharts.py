from django import template
from django.utils.safestring import mark_safe

import heapq
import itertools
import math
import textwrap

register = template.Library()

defaultcolors = [
    '#3366CC',
    '#DC3912',
    '#FF9900',
    '#109618',
    '#990099',
    '#3B3EAC',
    '#0099C6',
    '#DD4477',
    '#66AA00',
    '#B82E2E',
    '#316395',
    '#994499',
    '#22AA99',
    '#AAAA11',
    '#6633CC',
    '#E67300',
    '#8B0707',
    '#329262',
    '#5574A6',
    '#3B3EAC',
]


def _calculate_x(percent, radius):
    # Minus 25% to turn the graph 90 degrees making it look better
    return math.cos(2 * math.pi * (percent - 25) / 100) * radius


def _calculate_y(percent, radius):
    # Minus 25% to turn the graph 90 degrees making it look better
    return math.sin(2 * math.pi * (percent - 25) / 100) * radius


@register.simple_tag
def svgpiechart(svgdata, legendwidth=0):
    radius = 100
    colors = itertools.cycle(defaultcolors)

    t = template.loader.get_template('util/svgpiechart.svg')

    slices = []
    currpercent = 0

    total = sum(svgdata.values())

    if total > 0:
        for i, (k, v) in enumerate(svgdata.items()):
            thispercent = 100 * v / total
            slices.append({
                'startx': _calculate_x(currpercent, radius),
                'starty': _calculate_y(currpercent, radius),
                'endx': _calculate_x(currpercent + thispercent, radius),
                'endy': _calculate_y(currpercent + thispercent, radius),
                'centerx': _calculate_x(currpercent + thispercent / 2, radius / 1.8),
                'centery': _calculate_y(currpercent + thispercent / 2, radius / 1.8),
                'percent': thispercent > 5 and round(thispercent, 1) or 0,
                'color': next(colors),
                'largearc': thispercent > 50 and 1 or 0,
                'drawslice': thispercent > 0,
                'popup': '{}\n\n{} ({}%)'.format(k, v, round(thispercent, 1)),
                'legend': {
                    'y': -100 + (i + 1) * 20 - 10,
                    'text': k,
                },
            })
            currpercent += thispercent

    return t.render({
        'radius': radius,
        'slices': slices,
        'legendwidth': legendwidth,
    })


@register.simple_tag
def svgbarchart(svgdata, legend=True, wratio=2):
    t = template.loader.get_template('util/svgbarchart.svg')

    height = 100
    width = height * wratio
    itemwidth = width // len(svgdata)
    if legend:
        grpahratio = 0.65  # Estimate that mostly works?
    else:
        graphratio = 1 - 10 / height

    maxval = max([d['value'] for d in svgdata])
    roundedmax = math.ceil(maxval / 2) * 2

    if not roundedmax:
        # Graph is empty
        return t.render({
            'height': height,
            'width': width,
        })

    for i, s in enumerate(svgdata):
        s['leftpos'] = itemwidth * i
        s['height'] = int((s['value'] / roundedmax) * graphratio * height)
        s['negheight'] = -s['height']

    return t.render({
        'svgdata': svgdata,
        'height': height,
        'width': width,
        'bottom': graphratio * height,
        'legendheight': int((1 - graphratio) * height),
        'neglegendheight': int(-(1 - graphratio) * height),
        'itemwidth': itemwidth // 2,
        'negitemwidth': -1 * (itemwidth // 2),
        'gridlines': {
            str(roundedmax // 2): int(graphratio * height / 2),
            str(roundedmax): 0,
        },
    })


def _linreg(x, y):
    # Simple linear regression
    N = len(x)
    Sx = Sy = Sxx = Syy = Sxy = 0.0
    for x, y in zip(x, y):
        Sx = Sx + x
        Sy = Sy + y
        Sxx = Sxx + x * x
        Syy = Syy + y * y
        Sxy = Sxy + x * y
    det = Sxx * N - Sx * Sx
    return (Sxy * N - Sy * Sx) / det, (Sxx * Sy - Sx * Sxy) / det


@register.simple_tag
def svglinechart(xlabels, series, wratio=3, ylabel='', xlabel='', alwayszeroline=False, trendlines=False):
    colors = itertools.cycle(defaultcolors)

    t = template.loader.get_template('util/svglinechart.svg')

    width = 250
    height = width // wratio

    serieslen = len(xlabels)

    maxval = 0
    for s in series:
        s['maxval'] = max(s['values'])
    maxval = max(s['maxval'] for s in series)

    # XXX: Make this 20 configurable!
    roundingvalue = 20
    numgridlines = 6

    maxval = math.ceil(maxval / roundingvalue) * roundingvalue
    gridvals = [(x + 1) * maxval // numgridlines for x in range(numgridlines)]
    gridlines = [(v, height - int(height * v / maxval)) for v in gridvals]

    xvals = [20 + x * 200 / (serieslen - 1) for x in range(serieslen)]
    xgridvals = xlabels[::int(math.ceil(serieslen / 7))]
    xgridlines = xvals[::int(math.ceil(serieslen / 7))]
    xgridvals.append(xlabels[-1])
    xgridlines.append(xvals[-1])
    xgrid = zip(xgridvals, xgridlines)
    zerolineat = None
    if alwayszeroline and 0 not in xgridvals:
        try:
            ofs = xlabels.index(0)
            xgridvals.append(xlabels[ofs])
            xgridlines.append(xvals[ofs])
            zerolineat = xvals[ofs]
        except ValueError:
            pass

    for s in series:
        s['values'] = list(zip(
            xvals,
            [height - int(height * v / maxval) for v in s['values']],
            xlabels,
            s['values'],
        ))
        s['color'] = next(colors)

    legend = [{
        'label': textwrap.wrap(s['label'], 11)[:2],
        'color': s['color'],
        'ypos': i * 8 + 5,
    } for i, s in enumerate(heapq.nlargest(8, series, key=lambda s: s['maxval']))]

    # Trendlines will only be plotted against the first series
    if trendlines:
        a, b = _linreg([float(x[0]) for x in series[0]['values']], [float(y[1]) for y in series[0]['values']])
        trendline = ((xvals[0], b), (xvals[-1], a * xvals[-1] + b))
    else:
        trendline = None

    # X-wise:
    # 10 pixels label
    # 10 pixels scale
    # ---- axis
    # 200 pixels graph
    # --- exis
    # 30 pixels legend
    # --> total width: 250

    return t.render({
        'height': height,
        'halfheight': height / 2,
        'series': series,
        'ylabel': ylabel,
        'xlabel': xlabel,
        'gridlines': gridlines,
        'xgrid': xgrid,
        'zerolineat': zerolineat,
        'legend': legend,
        'trendline': trendline,
    })
