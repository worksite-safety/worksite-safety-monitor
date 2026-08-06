import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer, Label,
} from 'recharts';

const BarChartComponent = ({ data, keysAndColors, yAxisTitle }) => {
    return (
        <ResponsiveContainer width='100%' height={300}>
            <BarChart data={data} margin={{ top: 50}}>
                <CartesianGrid strokeDasharray='10 10 ' />
                <XAxis dataKey='date' >

                </XAxis>
                <YAxis type='number' allowDecimals={false}>
                    <Label
                        angle={-90}
                        position='insideLeft'
                        style={{ textAnchor: 'middle', fontSize: '14px', fontWeight: 'bold'}}
                    >
                        {yAxisTitle}
                    </Label>
                </YAxis>
                {/*
                  recharts 3 gave Tooltip a new `itemSorter: 'name'` default that
                  recharts 2 did not have, which reorders the rows alphabetically by
                  series label. Measured against recharts 2.15.4 the rows came out as
                  fall, armsUp, frontBending (the order of `keysAndColors`); under the v3
                  default they came out as armsUp, fall, frontBending. `null` restores
                  the payload order. There is deliberately no Legend on this chart.
                */}
                <Tooltip itemSorter={null} />
                {keysAndColors.map((keyAndColor, index) => (
                    <Bar
                        key={index}
                        dataKey={keyAndColor.key}
                        fill={keyAndColor.color}
                        barSize={75}
                    />
                ))}
            </BarChart>
        </ResponsiveContainer>
    );
};
export default BarChartComponent;