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
                </YAxis>                <Tooltip />
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