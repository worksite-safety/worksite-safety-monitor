import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
} from 'recharts';

const BarChartComponent = ({ data }) => {
    return (
        <ResponsiveContainer width='100%' height={300}>
            <BarChart data={data} margin={{ top: 50 }}>
                <CartesianGrid strokeDasharray='10 10 ' />
                <XAxis dataKey='date' />
                <YAxis type='number' allowDecimals={false} />
                <Tooltip />
                <Bar dataKey='totalIncome' fill='#3b82f6' barSize={75} />
            </BarChart>
        </ResponsiveContainer>
    );
};
export default BarChartComponent;