import {
    ResponsiveContainer,
    XAxis,
    CartesianGrid,
    Tooltip, LineChart, Legend, Line, Label, YAxis,
} from 'recharts';

const LineChartComponent = ({ data, keysAndColors, yAxisTitle }) => {
    console.log(data)
    return (
        <ResponsiveContainer width='100%' height={300}>
            <LineChart data={data} margin={{ top: 50 }}>
                <CartesianGrid strokeDasharray='3 3' />
                <XAxis dataKey='date' />
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
                  recharts 3 changed two sort defaults that recharts 2 did not have:
                  Tooltip gained `itemSorter: 'name'` and Legend gained
                  `itemSorter: 'value'`, both of which reorder the series alphabetically
                  by label. Measured against recharts 2.15.4: rows/entries came out as
                  fall, armsUp, frontBending (the order of `keysAndColors`); under the v3
                  defaults they came out as armsUp, fall, frontBending. `null` restores
                  the payload order.
                */}
                <Tooltip itemSorter={null} />
                <Legend itemSorter={null} />
                {keysAndColors.map((keyAndColor, index) => (
                    <Line
                        key={index}
                        type='monotone'
                        dataKey={keyAndColor.key}
                        stroke={keyAndColor.stroke}
                        fill={keyAndColor.fill}
                    />
                ))}
            </LineChart>
        </ResponsiveContainer>
    );
};
export default LineChartComponent;