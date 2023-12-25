import {IoBarChartSharp} from 'react-icons/io5';
import {FaWpforms} from 'react-icons/fa';
import {ImCalendar, ImProfile} from 'react-icons/im';
import {AiOutlineCar} from 'react-icons/ai';


const Links = () => {

    const links = [
        {
            id: 1,
            text: 'stats',
            path: '/',
            icon: <IoBarChartSharp/>,
        },
        {
            id: 2,
            text: 'all cars',
            path: 'all-cars',
            icon: <AiOutlineCar/>,
        },
        {
            id: 3,
            text: 'add car',
            path: 'add-car',
            icon: <FaWpforms/>,
        },
        {
            id: 4,
            text: 'profile',
            path: 'profile',
            icon: <ImProfile/>,
        },
        {
            id: 6,
            text: 'Reservations',
            path: 'all-reservations',
            icon: <ImCalendar/>,
        },

    ];
    return links;
}

export default Links;