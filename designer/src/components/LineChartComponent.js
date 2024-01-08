import {
    ResponsiveContainer,
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip, LineChart, Legend, Line,
} from 'recharts';

const LineChartComponent = ({ data }) => {
    console.log(data)
    return (
        <ResponsiveContainer width='100%' height={300}>
            <LineChart data={data} margin={{ top: 50 }}>
                <CartesianGrid strokeDasharray='3 3' />
                <XAxis dataKey='date' />
                <Tooltip />
                <Legend />
                <Line type='monotone' dataKey='fall' stroke='#1D2B53' fill='#B799FF' />
                <Line type='monotone' dataKey='armsUp' stroke='#7E2553' fill='#ACBCFF' />
                <Line type='monotone' dataKey='frontBending' stroke='#525CEB' fill='#AEE2FF' />

            </LineChart>
        </ResponsiveContainer>
    );
};
export default LineChartComponent;