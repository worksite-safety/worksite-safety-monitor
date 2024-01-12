import {
    ResponsiveContainer,
    XAxis,
    CartesianGrid,
    Tooltip, LineChart, Legend, Line,
} from 'recharts';

const LineChartComponent = ({ data, keysAndColors }) => {
    console.log(data)
    return (
        <ResponsiveContainer width='100%' height={300}>
            <LineChart data={data} margin={{ top: 50 }}>
                <CartesianGrid strokeDasharray='3 3' />
                <XAxis dataKey='date' />
                <Tooltip />
                <Legend />
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