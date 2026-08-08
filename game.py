import random
import os
import glob
import yaml
from typing import List, Optional, Dict, Any, Tuple, Set

# ------------------- Модели данных -------------------

class City:
    def __init__(self, name: str, tag: str):
        self.name = name
        self.tag = tag          # 'деревня', 'небольшой город', 'столица'
        self.neighbors: List['City'] = []

    def add_neighbor(self, other: 'City'):
        if other not in self.neighbors:
            self.neighbors.append(other)

    def __repr__(self):
        return self.name


class Outcome:
    def __init__(self, text: str, success_level: str, goal_achieved: Optional[str] = None):
        self.text = text
        self.success_level = success_level
        self.goal_achieved = goal_achieved


class Choice:
    def __init__(self, text: str, outcomes: List[Outcome]):
        self.text = text
        self.outcomes = outcomes

    def resolve(self) -> Outcome:
        return random.choice(self.outcomes)


class Event:
    def __init__(self, text: str, choices: List[Choice], tags: List[str], is_goal_event: bool = False):
        self.text = text
        self.choices = choices
        self.tags = tags
        self.is_goal_event = is_goal_event

    def matches_place(self, place_tags: Set[str]) -> bool:
        return all(tag in place_tags for tag in self.tags)


# ------------------- Загрузчик событий из файлов -------------------

class EventLoader:
    def __init__(self, events_dir: str = "events"):
        self.events_dir = events_dir
        self._tag_cache: Dict[str, List[Event]] = {}
        self._load_all()

    def _load_all(self):
        pattern = os.path.join(self.events_dir, "*.yaml")
        yaml_files = glob.glob(pattern) + glob.glob(os.path.join(self.events_dir, "*.yml"))
        for filepath in yaml_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if not data:
                        continue
                    tags = data.get("tags", [])
                    event = self._parse_event(data)
                    if event:
                        for tag in tags:
                            self._tag_cache.setdefault(tag, []).append(event)
            except Exception as e:
                print(f"Ошибка при загрузке файла {filepath}: {e}")

    def _parse_event(self, data: Dict[str, Any]) -> Optional[Event]:
        try:
            text = data["text"]
            is_goal = data.get("is_goal_event", False)
            tags = data.get("tags", [])
            choices_data = data.get("choices", [])
            choices = []
            for choice_item in choices_data:
                choice_text = choice_item["text"]
                outcomes_data = choice_item.get("outcomes", [])
                outcomes = []
                for out in outcomes_data:
                    level = out["success_level"]
                    goal = out.get("goal_achieved")
                    outcomes.append(Outcome(out["text"], level, goal))
                choices.append(Choice(choice_text, outcomes))
            return Event(text, choices, tags, is_goal)
        except KeyError as e:
            print(f"Ошибка в данных события: отсутствует поле {e}")
            return None

    def get_events_by_tag(self, tag: str) -> List[Event]:
        return self._tag_cache.get(tag, [])


# ------------------- Игровой движок -------------------

class Player:
    def __init__(self, start_city: City, goal: str):
        self.current_city = start_city
        self.goal = goal
        self.progress = 0
        self.history: List[Dict] = []
        self.game_over = False

    def move_to(self, city: City):
        self.current_city = city
        self.history.append({"action": "move", "to": city.name})

    def add_event_record(self, event_type: str, event: Event, choice: Choice, outcome: Outcome, progress_gained: int = 0):
        self.history.append({
            "type": event_type,
            "event": event.text,
            "choice": choice.text,
            "outcome": outcome.text,
            "success_level": outcome.success_level,
            "goal_achieved": outcome.goal_achieved,
            "progress_gained": progress_gained
        })

    def add_progress(self, amount: int = 1):
        self.progress = min(100, self.progress + amount)
        if self.progress >= 100:
            self.game_over = True


class Game:
    def __init__(self, loader: EventLoader):
        self.loader = loader
        self.cities, self.edge_tags = self._build_map()
        self.player = None
        self.current_edge_tag = None
        self.goals = ['wealth', 'fame', 'adventure']
        self.goal_names = {'wealth': 'Богатство', 'fame': 'Известность', 'adventure': 'Приключения'}

    def _build_map(self) -> Tuple[Dict[str, City], Dict[Tuple[str, str], str]]:
        city_tags = ['деревня', 'деревня', 'деревня', 'небольшой город', 'небольшой город', 'столица', 'столица']
        random.shuffle(city_tags)
        cities = {name: City(name, tag) for name, tag in zip(['A', 'B', 'C', 'D', 'E', 'F', 'G'], city_tags)}

        edges = [
            ('A', 'B'), ('A', 'C'), ('A', 'D'),
            ('B', 'C'), ('B', 'E'), ('B', 'F'),
            ('C', 'D'), ('C', 'G'),
            ('D', 'E'), ('D', 'F'),
            ('E', 'F'), ('E', 'G'),
            ('F', 'G')
        ]
        terrain_tags = ['лес', 'болото', 'море', 'джунгли', 'пустыня', 'горы']
        edge_tags = {}
        for u, v in edges:
            tag = random.choice(terrain_tags)
            key = tuple(sorted((u, v)))
            edge_tags[key] = tag
            cities[u].add_neighbor(cities[v])
            cities[v].add_neighbor(cities[u])

        return cities, edge_tags

    def get_edge_tag(self, city1: City, city2: City) -> Optional[str]:
        key = tuple(sorted((city1.name, city2.name)))
        return self.edge_tags.get(key)

    def start(self):
        start_city = random.choice(list(self.cities.values()))
        goal = random.choice(self.goals)
        self.player = Player(start_city, goal)
        self.current_edge_tag = None
        print(f"Добро пожаловать в игру-путешествие по сказочному миру!")
        print(f"Вы начинаете в городе {start_city.name} (тип: {start_city.tag}).")
        print(f"Ваша цель: {self.goal_names[goal]}.")
        print("Вы должны набрать 100 очков прогресса, совершая успешные действия в рамках вашей цели.")
        print("Каждый успех прибавляет 1 очко. Путешествуйте и создавайте свою историю!\n")

        self.city_events = self.loader.get_events_by_tag("city")
        self.travel_events = self.loader.get_events_by_tag("travel")

        if not self.city_events:
            print("ВНИМАНИЕ: Не найдено городских событий (тег 'city'). Проверьте папку events.")
        if not self.travel_events:
            print("ВНИМАНИЕ: Не найдено событий в пути (тег 'travel'). Проверьте папку events.")

        while not self.player.game_over:
            self.show_status()
            self.handle_move()
            if self.player.game_over:
                break
            if random.random() < 0.3 and self.travel_events:
                self.handle_travel_event()
                if self.player.game_over:
                    break
            if self.city_events:
                self.handle_city_event()
                if self.player.game_over:
                    break
            else:
                print("Нет доступных городских событий. Игра завершена.")
                self.player.game_over = True

        print("\n=== Игра завершена ===")
        if self.player.progress >= 100:
            print("Поздравляем! Вы достигли 100 очков прогресса и выполнили свою цель!")
        else:
            print("Игра прервана. Вы не достигли цели.")
        print(f"Итоговый прогресс: {self.player.progress}/100")
        print("Ваш путь:")
        for record in self.player.history:
            if record.get("action") == "move":
                print(f"  Переход в {record['to']}")
            else:
                print(f"  {record['type']}: {record['event']}")
                print(f"    Выбор: {record['choice']} -> {record['outcome']} ({record['success_level']})")
                if record.get("progress_gained", 0) > 0:
                    print(f"    Прогресс +{record['progress_gained']}")
        print(f"Цель: {self.goal_names[self.player.goal]} достигнута на {self.player.progress}%.")

    def show_status(self):
        print(f"\n--- Текущий город: {self.player.current_city.name} (тип: {self.player.current_city.tag}) ---")
        print(f"Прогресс к цели: {self.player.progress}/100")
        neighbors = self.player.current_city.neighbors
        print("Доступные направления:")
        for i, city in enumerate(neighbors):
            edge_tag = self.get_edge_tag(self.player.current_city, city)
            print(f"  {i+1}. {city.name} ({city.tag}) - путь через {edge_tag}")

    def handle_move(self):
        neighbors = self.player.current_city.neighbors
        while True:
            try:
                choice = int(input("Выберите номер города для перехода: "))
                if 1 <= choice <= len(neighbors):
                    target = neighbors[choice-1]
                    self.current_edge_tag = self.get_edge_tag(self.player.current_city, target)
                    self.player.move_to(target)
                    break
                else:
                    print("Неверный номер. Попробуйте снова.")
            except ValueError:
                print("Введите число.")

    def handle_travel_event(self):
        if self.current_edge_tag is None:
            return
        place_tags = {"travel", self.current_edge_tag}
        suitable = [ev for ev in self.travel_events if ev.matches_place(place_tags)]
        if not suitable:
            return
        event = random.choice(suitable)
        print(f"\n[В пути через {self.current_edge_tag}] {event.text}")
        self.process_event(event, "travel")

    def handle_city_event(self):
        place_tags = {"city", self.player.current_city.tag}
        suitable = [ev for ev in self.city_events if ev.matches_place(place_tags)]
        if not suitable:
            return
        event = random.choice(suitable)
        print(f"\n[Город {self.player.current_city.name} ({self.player.current_city.tag})] {event.text}")
        self.process_event(event, "city")

    def process_event(self, event: Event, event_type: str):
        for i, choice in enumerate(event.choices):
            print(f"  {i+1}. {choice.text}")
        while True:
            try:
                idx = int(input("Ваш выбор (номер): ")) - 1
                if 0 <= idx < len(event.choices):
                    chosen_choice = event.choices[idx]
                    break
                else:
                    print("Неверный номер.")
            except ValueError:
                print("Введите число.")

        outcome = chosen_choice.resolve()
        print(f"Результат: {outcome.text}")

        progress_gained = 0
        if outcome.goal_achieved == self.player.goal:
            self.player.add_progress(1)
            progress_gained = 1
            print(f"Прогресс +1! (текущий: {self.player.progress}/100)")

        self.player.add_event_record(event_type, event, chosen_choice, outcome, progress_gained)

        if self.player.progress >= 100:
            print("Поздравляем! Вы достигли 100 очков прогресса и выполнили свою цель!")
            self.player.game_over = True


# ------------------- Запуск -------------------

if __name__ == "__main__":
    loader = EventLoader("events")
    game = Game(loader)
    game.start()