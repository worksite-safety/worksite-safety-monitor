import { act, fireEvent, render } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import AreaChartComponent from './AreaChart';
import BarChartComponent from './BarChart';
import LineChartComponent from './LineChartComponent';
import PieChartComponent from './PieChartComponent';

/*
 * These tests exist because the recharts 2 -> 3 upgrade is a UX-preservation job, not a
 * feature: the brief was that the charts must look exactly as they did. Nothing else in
 * the suite renders a chart, so without these a colour, a series or the legend could go
 * missing and every test would still pass.
 *
 * Every expected value below was MEASURED by rendering the same component against
 * recharts 2.15.4 and against 3.10.1 and diffing the SVG, not read off the docs. Where
 * the two versions disagreed the component was changed to keep the recharts 2 output --
 * see the `itemSorter` comments in AreaChart/BarChart/LineChartComponent.
 */

function rect(width, height) {
  return {
    width, height, top: 0, left: 0,
    right: width, bottom: height, x: 0, y: 0,
    toJSON() {},
  };
}

beforeAll(() => {
  // recharts' ResponsiveContainer bails out of measuring entirely unless ResizeObserver
  // exists, and then reads getBoundingClientRect once. jsdom has neither, so a chart
  // measures 0x0 and renders nothing at all. Give the container a real size, and the
  // legend a realistic one -- a blanket stub would let the legend claim the full 300px
  // and collapse the plot area to zero height.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  Element.prototype.getBoundingClientRect = function () {
    const cls = typeof this.className === 'string' ? this.className : '';
    if (cls.includes('recharts-responsive-container')) return rect(800, 300);
    if (cls.includes('recharts-legend-wrapper')) return rect(800, 24);
    if (cls.includes('recharts-wrapper')) return rect(800, 300);
    return rect(0, 0);
  };
  // recharts 3 defaults every graphical item to isAnimationActive: 'auto', which resolves
  // to `!prefersReducedMotion`. Its entry animations never complete under jsdom -- the
  // bars, areas and lines stay unrendered forever -- so declare reduced motion and assert
  // the settled frame, which is the one that has to match recharts 2.
  window.matchMedia = (query) => ({
    matches: /prefers-reduced-motion/.test(query),
    media: query,
    onchange: null,
    addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {},
    dispatchEvent() { return false; },
  });
});

async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
}

const data = [
  { date: '2024-01-01', fall: 1, armsUp: 2, frontBending: 3 },
  { date: '2024-01-02', fall: 4, armsUp: 5, frontBending: 6 },
  { date: '2024-01-03', fall: 0, armsUp: 7, frontBending: 2 },
];

/*
 * Copied verbatim from ChartsContainer, which is the caller and owns these arrays. They
 * are a cross-module contract: the keys are the event taxonomy shared with the Java
 * engine and the Python detector, and the hex values are the agreed palette. If a rename
 * or a recolour ever lands in ChartsContainer these fixtures must be updated to match --
 * they are not free-floating test data.
 */
const keysAndColorsCountableBar = [
  { key: 'fall', color: '#B799FF' },
  { key: 'armsUp', color: '#ACBCFF' },
  { key: 'frontBending', color: '#AEE2FF' },
];
const keysAndColorsCountableEventsLineChart = [
  { key: 'fall', stroke: '#1D2B53', fill: '#B799FF' },
  { key: 'armsUp', stroke: '#7E2553', fill: '#ACBCFF' },
  { key: 'frontBending', stroke: '#525CEB', fill: '#AEE2FF' },
];
const keysAndColorsCountableAreaChart = [
  { key: 'fall', stroke: '#92C7CF', fill: '#B799FF', strokeDasharray: '5 5' },
  { key: 'armsUp', stroke: '#AAD7D9', fill: '#ACBCFF', strokeDasharray: '5 5' },
  { key: 'frontBending', stroke: '#86B6F6', fill: '#AEE2FF', strokeDasharray: '5 5' },
];

const Y_AXIS_TITLE = 'Total Count Of Events';

function attrs(container, selector, name) {
  return [...container.querySelectorAll(selector)].map((n) => n.getAttribute(name));
}

function legendLabels(container) {
  return [...container.querySelectorAll('.recharts-legend-item-text')].map((n) => n.textContent);
}

/**
 * The rotated y-axis title is a <Label> passed as a child of <YAxis>. recharts 3 reworked
 * how axes render their children -- the label now goes through a CartesianLabelContext
 * and lands in a different SVG group -- so assert the rendered text element directly
 * rather than trusting that the child was honoured.
 */
function expectYAxisTitle(container) {
  const label = container.querySelector('.recharts-label');
  expect(label).not.toBeNull();
  expect(label.textContent).toBe(Y_AXIS_TITLE);
  // angle={-90} arrives as a rotate() transform, not as an `angle` attribute.
  expect(label.getAttribute('transform')).toMatch(/^rotate\(-90,/);
  expect(label.style.textAnchor).toBe('middle');
  expect(label.style.fontSize).toBe('14px');
  expect(label.style.fontWeight).toBe('bold');
}

/**
 * Hover the plot to open the tooltip and return its text. recharts 3 added an
 * `itemSorter: 'name'` default to Tooltip that recharts 2 did not have; this is how we
 * catch it if the override is ever dropped.
 */
async function tooltipTextAfterHover(container) {
  const wrapper = container.querySelector('.recharts-wrapper');
  const event = { clientX: 430, clientY: 150, pageX: 430, pageY: 150, bubbles: true };
  await act(async () => {
    fireEvent.mouseOver(wrapper, event);
    fireEvent.mouseMove(wrapper, event);
    fireEvent.pointerMove(wrapper, { ...event, pointerId: 1, pointerType: 'mouse' });
  });
  await settle();
  return container.querySelector('.recharts-default-tooltip').textContent;
}

describe('AreaChartComponent', () => {
  it('draws one filled area and one stroked curve per key, in the declared colours', async () => {
    const { container } = render(
      <AreaChartComponent
        data={data}
        keysAndColors={keysAndColorsCountableAreaChart}
        yAxisTitle={Y_AXIS_TITLE}
      />,
    );
    await settle();

    expect(attrs(container, '.recharts-area-area', 'fill')).toEqual(
      ['#B799FF', '#ACBCFF', '#AEE2FF'],
    );
    expect(attrs(container, '.recharts-area-curve', 'stroke')).toEqual(
      ['#92C7CF', '#AAD7D9', '#86B6F6'],
    );
    // strokeDasharray comes from the prop, and must survive on both the fill and the curve.
    expect(attrs(container, '.recharts-area-curve', 'stroke-dasharray')).toEqual(
      ['5 5', '5 5', '5 5'],
    );
    // Area's own fill-opacity default. Measured at 0.6 on both 2.15.4 and 3.10.1.
    expect(attrs(container, '.recharts-area-area', 'fill-opacity')).toEqual(
      ['0.6', '0.6', '0.6'],
    );
  });

  it('keeps the grid, the axes, the rotated title and a legend', async () => {
    const { container } = render(
      <AreaChartComponent
        data={data}
        keysAndColors={keysAndColorsCountableAreaChart}
        yAxisTitle={Y_AXIS_TITLE}
      />,
    );
    await settle();

    expect(
      container.querySelector('.recharts-cartesian-grid line').getAttribute('stroke-dasharray'),
    ).toBe('3 3');
    expect(container.querySelector('.recharts-responsive-container').style.height).toBe('300px');
    expectYAxisTitle(container);
    expect(container.querySelector('.recharts-xAxis')).not.toBeNull();
    expect(container.querySelector('.recharts-yAxis')).not.toBeNull();
    expect(container.querySelector('.recharts-legend-wrapper')).not.toBeNull();
  });

  it('lists legend entries in the order ChartsContainer declares them', async () => {
    const { container } = render(
      <AreaChartComponent
        data={data}
        keysAndColors={keysAndColorsCountableAreaChart}
        yAxisTitle={Y_AXIS_TITLE}
      />,
    );
    await settle();

    // recharts 2.15.4 produced exactly this order. recharts 3's `itemSorter: 'value'`
    // default would sort it alphabetically to armsUp, fall, frontBending.
    expect(legendLabels(container)).toEqual(['fall', 'armsUp', 'frontBending']);
  });
});

describe('BarChartComponent', () => {
  it('draws a bar per non-zero value in the declared fill, 75px wide', async () => {
    const { container } = render(
      <BarChartComponent
        data={data}
        keysAndColors={keysAndColorsCountableBar}
        yAxisTitle={Y_AXIS_TITLE}
      />,
    );
    await settle();

    const bars = [...container.querySelectorAll('.recharts-rectangle')];
    // 3 days x 3 series, less the one zero value (fall on 2024-01-03), which draws nothing.
    expect(bars).toHaveLength(8);
    expect(bars.every((b) => b.getAttribute('width') === '75')).toBe(true);
    expect(new Set(bars.map((b) => b.getAttribute('fill')))).toEqual(
      new Set(['#B799FF', '#ACBCFF', '#AEE2FF']),
    );
  });

  it('uses the "10 10 " grid and carries no legend', async () => {
    const { container } = render(
      <BarChartComponent
        data={data}
        keysAndColors={keysAndColorsCountableBar}
        yAxisTitle={Y_AXIS_TITLE}
      />,
    );
    await settle();

    // The trailing space is what ships today; it is passed straight through to the DOM.
    expect(
      container.querySelector('.recharts-cartesian-grid line').getAttribute('stroke-dasharray'),
    ).toBe('10 10 ');
    expectYAxisTitle(container);
    // The bar chart deliberately has no <Legend />, unlike the area and line charts.
    expect(container.querySelector('.recharts-legend-wrapper')).toBeNull();
  });

  it('orders tooltip rows by declaration, not alphabetically', async () => {
    const { container } = render(
      <BarChartComponent
        data={data}
        keysAndColors={keysAndColorsCountableBar}
        yAxisTitle={Y_AXIS_TITLE}
      />,
    );
    await settle();

    // Measured against recharts 2.15.4. recharts 3's `itemSorter: 'name'` Tooltip default
    // would render this as "armsUp : 5fall : 4frontBending : 6".
    expect(await tooltipTextAfterHover(container)).toBe(
      '2024-01-02fall : 4armsUp : 5frontBending : 6',
    );
  });
});

describe('LineChartComponent', () => {
  it('draws one curve per key in the declared stroke', async () => {
    const { container } = render(
      <LineChartComponent
        data={data}
        keysAndColors={keysAndColorsCountableEventsLineChart}
        yAxisTitle={Y_AXIS_TITLE}
      />,
    );
    await settle();

    expect(attrs(container, '.recharts-line-curve', 'stroke')).toEqual(
      ['#1D2B53', '#7E2553', '#525CEB'],
    );
    // dot={true} is the Line default on both versions: one dot per point per series.
    expect(container.querySelectorAll('.recharts-line-dot')).toHaveLength(9);
  });

  it('keeps the grid, the rotated title and the legend order', async () => {
    const { container } = render(
      <LineChartComponent
        data={data}
        keysAndColors={keysAndColorsCountableEventsLineChart}
        yAxisTitle={Y_AXIS_TITLE}
      />,
    );
    await settle();

    expect(
      container.querySelector('.recharts-cartesian-grid line').getAttribute('stroke-dasharray'),
    ).toBe('3 3');
    expectYAxisTitle(container);
    expect(legendLabels(container)).toEqual(['fall', 'armsUp', 'frontBending']);
  });

  it('orders tooltip rows by declaration, not alphabetically', async () => {
    const { container } = render(
      <LineChartComponent
        data={data}
        keysAndColors={keysAndColorsCountableEventsLineChart}
        yAxisTitle={Y_AXIS_TITLE}
      />,
    );
    await settle();

    expect(await tooltipTextAfterHover(container)).toBe(
      '2024-01-02fall : 4armsUp : 5frontBending : 6',
    );
  });
});

describe('PieChartComponent', () => {
  const pieChartData = [
    { name: 'FALL', value: 3 },
    { name: 'ARMS_UP', value: 5 },
    { name: 'FRONT_BEND', value: 0 },
  ];

  it('colours the slices from COLORS in data order', async () => {
    const { container } = render(<PieChartComponent pieChartData={pieChartData} />);
    await settle();

    // COLORS = ['#86b6f6', '#92c7cf', '#b799ff']. The zero-value slice draws no sector.
    expect(attrs(container, '.recharts-sector', 'fill')).toEqual(['#86b6f6', '#92c7cf']);
  });

  it('renders the custom label with its friendly name and rounded percent', async () => {
    const { container } = render(<PieChartComponent pieChartData={pieChartData} />);
    await settle();

    const labels = [...container.querySelectorAll('text[fill="black"]')].map((n) => n.textContent);
    // labelMappings maps FALL -> Fall and ARMS_UP -> Arms; percent is a 0..1 fraction on
    // both recharts versions, so (percent * 100).toFixed(0) still reads 38 / 63.
    expect(labels).toEqual(['Fall: 38%', 'Arms: 63%']);
  });

  it('renders no label for a zero-percent slice', async () => {
    const { container } = render(<PieChartComponent pieChartData={pieChartData} />);
    await settle();

    // renderCustomizedLabel returns null when percent === 0, so FRONT_BEND gets no text.
    expect(container.textContent).not.toMatch(/Bending/);
  });

  it('keeps its 400x400 chart centred in a 35vh flex box', async () => {
    const { container } = render(<PieChartComponent pieChartData={pieChartData} />);
    await settle();

    const wrapper = container.firstChild;
    expect(wrapper.style.display).toBe('flex');
    expect(wrapper.style.justifyContent).toBe('center');
    expect(wrapper.style.alignItems).toBe('center');
    expect(wrapper.style.height).toBe('35vh');

    const svg = container.querySelector('svg.recharts-surface');
    expect(svg.getAttribute('width')).toBe('400');
    expect(svg.getAttribute('height')).toBe('400');
  });
});
