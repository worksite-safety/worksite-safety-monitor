import StatItem from './StatItem';
import {CiCircleQuestion, CiCircleAlert, CiWarning} from 'react-icons/ci';
import Wrapper from '../assets/wrappers/StatsContainer';
import { useSelector } from 'react-redux';
import {store} from "../store";

const StatsContainer = () => {
    const { stats } = useSelector((store)
       // => store.allCars
    );

    const defaultStats = [
        {
            title: 'Green Violances',
            //count: stats.totalUsers || 0,
            icon: <CiCircleQuestion />,
            color: '#89e949',
            bcg: '#fcefc7',
        },
        {
            title: 'Blue Violances',
           // count: stats.totalReservations || 0,
            icon: <CiCircleAlert />,
            color: '#647acb',
            bcg: '#e0e8f9',
        },
        {
            title: 'Red Violances',
           // count: stats.totalCars || 0,
            icon: <CiWarning />,
            color: '#ff0000',
            bcg: '#ffeeee',
        },
    ];

    return (
        <Wrapper>
            {defaultStats.map((item, index) => {
                return <StatItem key={index} {...item} />;
            })}
        </Wrapper>
    );
};
export default StatsContainer;