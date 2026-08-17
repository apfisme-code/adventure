import random
import os
import glob
import yaml
import re
from typing import List, Optional, Dict, Any, Tuple, Set, Union

# ------------------- Загрузка конфигурации статусов -------------------

def load_statuses_config(filepath: str = "statuses.yaml") -> Dict[str, Dict]:
    with open(filepath, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get("statuses", {})

def load_character(filepath: str) -> Dict:
    with open(filepath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_quest(filepath: str) -> Dict:
    with open(filepath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_all_quests(quests_dir: str = "quests") -> Dict[str, Dict]:
    """Загружает все квесты из папки, возвращает словарь {id: quest_data}."""
    quests = {}
    pattern = os.path.join(quests_dir, "*.yaml")
    yaml_files = glob.glob(pattern) + glob.glob(os.path.join(quests_dir, "*.yml"))
    for filepath in yaml_files:
        try:
            data = load_quest(filepath)
            if data and "id" in data:
                quests[data["id"]] = data
        except Exception as e:
            print(f"Ошибка загрузки квеста {filepath}: {e}")
    return quests

# ------------------- Модели данных -------------------

class City:
    def __init__(self, name: str, tag: str):
        self.name = name
        self.tag = tag
        self.neighbors: List['City'] = []

    def add_neighbor(self, other: 'City'):
        if other not in self.neighbors:
            self.neighbors.append(other)

    def __repr__(self):
        return self.name


class Condition:
    def __init__(self, status: str, operator: str, value: Union[int, bool]):
        self.status = status
        self.operator = operator
        self.value = value

    def check(self, player_statuses: Dict[str, Union[int, bool]]) -> bool:
        current = player_statuses.get(self.status)
        if current is None:
            return False
        if self.operator == "==":
            return current == self.value
        elif self.operator == "!=":
            return current != self.value
        elif self.operator == ">=":
            return current >= self.value
        elif self.operator == "<=":
            return current <= self.value
        elif self.operator == ">":
            return current > self.value
        elif self.operator == "<":
            return current < self.value
        else:
            return False

    @staticmethod
    def parse(condition_dict: Dict[str, str]) -> 'Condition':
        status = condition_dict.get('status', None)
        operator = condition_dict.get('operator', None)
        value = condition_dict.get('value', None)

        if status is None or operator is None or value is None:
            raise ValueError(f"Некорректное условие: {condition_dict}")

        if not re.match(r'([><=!]+)(.+)', operator):
            raise ValueError(f"Некорректный оператор: {operator} в условии: {condition_dict}")

        return Condition(status, operator, value)

    def __repr__(self):
        return f"{self.status} {self.operator} {self.value}"


class Outcome:
    def __init__(self, text: str, success_level: str,
                 status_changes: Optional[Dict[str, Union[int, bool]]] = None,
                 add_quest: Optional[str] = None,
                 complete_quest: bool = False,
                 next_event: Optional[str] = None):
        self.text = text
        self.success_level = success_level
        self.status_changes = status_changes or {}
        self.add_quest = add_quest
        self.complete_quest = complete_quest
        self.next_event = next_event  # может быть id события или "tag:тег"


class Choice:
    def __init__(self, text: str, outcomes: List[Outcome], requires: Optional[List[Condition]] = None):
        self.text = text
        self.outcomes = outcomes
        self.requires = requires or []

    def resolve(self) -> Outcome:
        return random.choice(self.outcomes)


class Event:
    def __init__(self, event_id: str, text: str, choices: List[Choice], tags: List[str],
                  is_goal_event: bool = False, requires: Optional[List[Condition]] = None):
        self.id = event_id
        self.text = text
        self.choices = choices
        self.tags = tags
        self.is_goal_event = is_goal_event
        self.requires = requires or []

    def matches_place(self, place_tags: Set[str]) -> bool:
        return all(tag in place_tags for tag in self.tags)

# ------------------- Система квестов -------------------

class Quest:
    def __init__(self, quest_id: str, name: str, description: str,
                 conditions: List[Condition],
                 on_complete: Dict, on_fail: Dict = None):
        self.id = quest_id
        self.name = name
        self.description = description
        self.conditions = conditions
        self.on_complete = on_complete or {}
        self.on_fail = on_fail or {}

    @staticmethod
    def from_data(data: Dict) -> 'Quest':
        conditions = [Condition.parse(c) for c in data.get("conditions", [])]
        on_complete = data.get("on_complete", {})
        on_fail = data.get("on_fail", {})
        return Quest(data["id"], data["name"], data["description"],
                     conditions, on_complete, on_fail)

    def check_completion(self, player_statuses: Dict[str, Union[int, bool]]) -> bool:
        return all(c.check(player_statuses) for c in self.conditions)

# ------------------- Загрузчик событий из файлов -------------------

class EventLoader:
    def __init__(self, events_dir: str = "events"):
        self.events_dir = events_dir
        self._tag_cache: Dict[str, List[Event]] = {}
        self._id_cache: Dict[str, Event] = {}
        self._load_all()

    def _load_all(self):
        pattern = os.path.join(self.events_dir, "**", "*.yaml")
        yaml_files = glob.glob(pattern, recursive=True) + glob.glob(os.path.join(self.events_dir, "**", "*.yml"), recursive=True)
        for filepath in yaml_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if not data:
                        continue
                    # Определяем id: либо из поля, либо из имени файла без расширения
                    event_id = data.get("id", os.path.splitext(os.path.basename(filepath))[0])
                    tags = data.get("tags", [])
                    event = self._parse_event(data, event_id)
                    if event:
                        self._id_cache[event_id] = event
                        for tag in tags:
                            self._tag_cache.setdefault(tag, []).append(event)
            except Exception as e:
                print(f"Ошибка при загрузке файла {filepath}: {e}")

    def _parse_event(self, data: Dict[str, Any], event_id: str) -> Optional[Event]:
        try:
            text = data["text"]
            is_goal = data.get("is_goal_event", False)
            tags = data.get("tags", [])
            requires = self._parse_conditions(data.get("requires", []))
            choices_data = data.get("choices", [])
            choices = []
            for choice_item in choices_data:
                choice_text = choice_item["text"]
                choice_requires = self._parse_conditions(choice_item.get("requires", []))
                outcomes_data = choice_item.get("outcomes", [])
                outcomes = []
                for out in outcomes_data:
                    level = out["success_level"]
                    changes = out.get("status_changes", {})
                    add_quest = out.get("add_quest")
                    complete_quest = out.get("complete_quest", False)
                    next_event = out.get("next_event")  # строка или None
                    outcomes.append(Outcome(out["text"], level, changes, add_quest, complete_quest, next_event))
                choices.append(Choice(choice_text, outcomes, choice_requires))
            return Event(event_id, text, choices, tags, is_goal, requires)
        except KeyError as e:
            print(f"Ошибка в данных события {event_id}: отсутствует поле {e}")
            return None

    def _parse_conditions(self, raw_conditions: List[Dict[str, str]]) -> List[Condition]:
        conditions = []
        for cond_dict in raw_conditions:
            conditions.append(Condition.parse(cond_dict))
        return conditions

    def get_events_by_tag(self, tag: str) -> List[Event]:
        return self._tag_cache.get(tag, [])

    def get_event_by_id(self, event_id: str) -> Optional[Event]:
        return self._id_cache.get(event_id)

    def get_random_event_by_tag(self, tag: str) -> Optional[Event]:
        events = self._tag_cache.get(tag, [])
        if not events:
            return None
        return random.choice(events)


# ------------------- Игровой движок -------------------

class Player:
    def __init__(self, character_data: Dict, statuses_config: Dict[str, Dict],
                 quests_db: Dict[str, Dict]):
        self.name = character_data["name"]
        self.description = character_data["description"]
        self.statuses_config = statuses_config
        self.quests_db = quests_db
        # Инициализация статусов
        self.statuses = {}
        for name, info in statuses_config.items():
            if info["type"] == "numeric":
                self.statuses[name] = info.get("default", 0)
            elif info["type"] == "boolean":
                self.statuses[name] = info.get("default", False)
        # Переопределяем начальными из персонажа
        if "statuses" in character_data:
            for stat, val in character_data["statuses"].items():
                if stat in self.statuses:
                    self.statuses[stat] = val

        # Квесты: стек (последний – текущий)
        self.quest_stack: List[Quest] = []
        # Добавляем начальный квест
        start_quest_id = character_data["goal_quest"]
        if start_quest_id in self.quests_db:
            self.quest_stack.append(Quest.from_data(self.quests_db[start_quest_id]))

        self.current_city = None  # будет установлен позже
        self.history: List[Dict] = []
        self.game_over = False
        self.in_event_chain = False  # флаг, что мы внутри цепочки событий (нельзя перемещаться)

    def move_to(self, city: City):
        if self.in_event_chain:
            print("Вы не можете перемещаться, пока не завершите цепочку событий!")
            return False
        self.current_city = city
        self.history.append({"action": "move", "to": city.name})
        return True

    def add_event_record(self, event_type: str, event: Event, choice: Choice,
                         outcome: Outcome, status_changes: Optional[Dict[str, Union[int, bool]]] = None):
        self.history.append({
            "type": event_type,
            "event": event.text,
            "choice": choice.text,
            "outcome": outcome.text,
            "success_level": outcome.success_level,
            "status_changes": status_changes or {}
        })

    def apply_status_changes(self, changes: Dict[str, Union[int, bool]]):
        for status, value in changes.items():
            if status not in self.statuses_config:
                continue
            info = self.statuses_config[status]
            if info["type"] == "numeric":
                if not isinstance(value, int):
                    continue
                current = self.statuses.get(status, 0)
                new_value = current + value
                min_val = info.get("min", 0)
                max_val = info.get("max", 10)
                if new_value < min_val:
                    new_value = min_val
                if new_value > max_val:
                    new_value = max_val
                self.statuses[status] = new_value
            elif info["type"] == "boolean":
                if not isinstance(value, bool):
                    continue
                self.statuses[status] = value

    def has_conditions(self, conditions: List[Condition]) -> bool:
        return all(cond.check(self.statuses) for cond in conditions)

    def get_current_quest(self) -> Optional[Quest]:
        if self.quest_stack:
            return self.quest_stack[-1]
        return None

    def complete_current_quest(self) -> bool:
        """Пытается завершить квест (проверяет условия). Возвращает True, если завершён."""
        quest = self.get_current_quest()
        if quest is None or not quest.check_completion(self.statuses):
            return False
        # Завершаем квест
        # Применяем on_complete
        if "status_changes" in quest.on_complete:
            self.apply_status_changes(quest.on_complete["status_changes"])
        # Добавляем новый квест, если указан
        next_quest_id = quest.on_complete.get("add_quest")
        if next_quest_id and next_quest_id in self.quests_db:
            new_quest = Quest.from_data(self.quests_db[next_quest_id])
            self.quest_stack.append(new_quest)
        # Удаляем текущий из стека
        self.quest_stack.remove(quest)
        return True

    def check_win_condition(self) -> bool:
        """Победа, если стек квестов пуст."""
        return len(self.quest_stack) == 0


class Game:

    def __init__(self, loader: EventLoader, statuses_config: Dict[str, Dict],
                 quests_db: Dict[str, Dict], characters_dir: str = "characters"):
        self.loader = loader
        self.statuses_config = statuses_config
        self.quests_db = quests_db
        self.characters_dir = characters_dir
        self.cities, self.edge_tags = self._build_map()
        self.player = None
        self.current_edge_tag = None

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

    def get_available_events(self, events: List[Event]) -> List[Event]:
        return [ev for ev in events if self.player.has_conditions(ev.requires)]

    def get_available_choices(self, choices: List[Choice]) -> List[Choice]:
        return [ch for ch in choices if self.player.has_conditions(ch.requires)]

    def print_statuses(self, prefix: str = "Текущие статусы"):
        if self.player.statuses:
            parts = []
            for name, value in sorted(self.player.statuses.items()):
                if isinstance(value, bool):
                    parts.append(f"{name}: {'да' if value else 'нет'}")
                else:
                    parts.append(f"{name}: {value}")
            print(f"{prefix}: {', '.join(parts)}")
        else:
            print(f"{prefix}: нет")

    def print_quests(self):
        if self.player.quest_stack:
            print("Активные квесты (последний – текущий):")
            for i, q in enumerate(self.player.quest_stack):
                marker = "→ " if i == len(self.player.quest_stack)-1 else "  "
                print(f"  {marker}{q.name}: {q.description}")
        else:
            print("Нет активных квестов. Победа!")

    def start(self):
        # Загружаем всех персонажей
        char_files = glob.glob(os.path.join(self.characters_dir, "*.yaml")) + \
                     glob.glob(os.path.join(self.characters_dir, "*.yml"))
        if not char_files:
            print("Нет файлов персонажей в папке characters/")
            return
        # Выбираем случайного персонажа
        char_file = random.choice(char_files)
        character_data = load_character(char_file)
        print(f"Вы играете за {character_data['name']}: {character_data['description']}")

        self.player = Player(character_data, self.statuses_config, self.quests_db)
        start_city_name = character_data.get("start_city", "A")
        if start_city_name in self.cities:
            self.player.current_city = self.cities[start_city_name]
        else:
            self.player.current_city = random.choice(list(self.cities.values()))

        self.current_edge_tag = None

        print(f"Добро пожаловать в игру-путешествие по сказочному миру!")
        print(f"Вы начинаете в городе {self.player.current_city.name} (тип: {self.player.current_city.tag}).")
        print("Ваша цель: выполнить все квесты.\n")
        print("Путешествуйте, делайте выборы, развивайте свои навыки и достигните цели!\n")

        self.city_events = self.loader.get_events_by_tag("city")
        self.travel_events = self.loader.get_events_by_tag("travel")
        
        if not self.city_events:
            print("ВНИМАНИЕ: Не найдено городских событий (тег 'city').")
        if not self.travel_events:
            print("ВНИМАНИЕ: Не найдено событий в пути (тег 'travel').")

        while not self.player.game_over:
            if not self.player.in_event_chain:
                self.show_status()
                self.handle_move()
                if self.player.game_over:
                    break
                # Событие в пути с вероятностью 30%
                if random.random() < 0.3 and self.travel_events:
                    self.handle_travel_event()
                    if self.player.game_over:
                        break
                # Городское событие
                if self.city_events:
                    self.handle_city_event()
                    if self.player.game_over:
                        break
                else:
                    print("Нет доступных городских событий. Игра завершена.")
                    self.player.game_over = True
            else:
                # Если мы в цепочке, не даём перемещаться, только обрабатываем следующее событие
                # (у нас уже есть next_event, которое мы обработаем в process_event)
                # Но мы должны ждать, пока цепочка не закончится.
                # В process_event мы будем вызывать следующий, и он установит флаг обратно.
                pass

        print("\n=== Игра завершена ===")
        if self.player.check_win_condition():
            print("Поздравляем! Вы выполнили все квесты и победили!")        
        else:
            print("Вы не достигли цели.")
        self.print_statuses("Финальные статусы")
        self.print_quests()
        print("Ваш путь:")
        for record in self.player.history:
            if record.get("action") == "move":
                print(f"  Переход в {record['to']}")
            else:
                print(f"  {record['type']}: {record['event']}")
                print(f"    Выбор: {record['choice']} -> {record['outcome']} ({record['success_level']})")
                if record.get("status_changes"):
                    changes = record["status_changes"]
                    for stat, delta in changes.items():
                        if isinstance(delta, bool):
                            print(f"    {stat}: {'установлен' if delta else 'сброшен'}")
                        else:
                            print(f"    {stat}: {delta:+d}")

    def show_status(self):
        print(f"\n--- Текущий город: {self.player.current_city.name} (тип: {self.player.current_city.tag}) ---")
        self.print_statuses()
        self.print_quests()
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
                    if self.player.move_to(target):
                        print(f"\nВы перешли в {target.name}.")
                        self.print_statuses("Ваши статусы после перемещения")
                        break
                else:
                    print("Неверный номер. Попробуйте снова.")
            except ValueError:
                print("Введите число.")

    def handle_travel_event(self):
        if self.current_edge_tag is None:
            return
        place_tags = {"travel", self.current_edge_tag}
        candidates = [ev for ev in self.travel_events if ev.matches_place(place_tags)]
        available = self.get_available_events(candidates)
        if not available:
            print(f"Нет подходящих событий в пути через {self.current_edge_tag}.")
            return
        event = random.choice(available)
        print(f"\n[В пути через {self.current_edge_tag}] {event.text}")
        self.process_event(event, "travel")

    def handle_city_event(self):
        place_tags = {"city", self.player.current_city.tag}
        candidates = [ev for ev in self.city_events if ev.matches_place(place_tags)]
        available = self.get_available_events(candidates)
        if not available:
            print(f"Нет подходящих событий в городе {self.player.current_city.name}.")
            return
        event = random.choice(available)
        print(f"\n[Город {self.player.current_city.name} ({self.player.current_city.tag})] {event.text}")
        self.process_event(event, "city")

    def process_event(self, event: Event, event_type: str):
        # Устанавливаем флаг цепочки (если событие имеет next_event, он останется)
        self.player.in_event_chain = True

        available_choices = self.get_available_choices(event.choices)
        if not available_choices:
            print("Нет доступных вариантов для ваших статусов. Событие пропущено.")
            self.player.in_event_chain = False
            return

        for i, choice in enumerate(available_choices):
            req_str = f" (требуется: {', '.join(str(c) for c in choice.requires)})" if choice.requires else ""
            print(f"  {i+1}. {choice.text}{req_str}")

        while True:
            try:
                idx = int(input("Ваш выбор (номер): ")) - 1
                if 0 <= idx < len(available_choices):
                    chosen_choice = available_choices[idx]
                    break
                else:
                    print("Неверный номер.")
            except ValueError:
                print("Введите число.")

        outcome = chosen_choice.resolve()
        print(f"Результат: {outcome.text}")

        # Применяем изменения статусов
        if outcome.status_changes:
            old_values = {s: self.player.statuses.get(s) for s in outcome.status_changes.keys()}
            self.player.apply_status_changes(outcome.status_changes)
            for status, delta in outcome.status_changes.items():
                new_val = self.player.statuses.get(status)
                old_val = old_values.get(status)
                if isinstance(delta, bool):
                    print(f"{status}: {'да' if new_val else 'нет'} (было: {'да' if old_val else 'нет'})")
                else:
                    print(f"{status}: {old_val} → {new_val} ({delta:+d})")
            self.print_statuses("Обновлённые статусы")
        else:
            self.print_statuses("Ваши статусы")

        # Обработка квестов
        if outcome.complete_quest:
            if self.player.complete_current_quest():
                if self.player.check_win_condition():
                    print("Поздравляем! Вы выполнили все квесты! Победа!")
                    self.player.game_over = True
                    self.player.add_event_record(event_type, event, chosen_choice, outcome)
                    return
            else:
                quest = self.player.get_current_quest()
                if quest is not None:
                    print(f"Условия квеста '{quest.name}' не выполнены.")

        if outcome.add_quest:
            quest_id = outcome.add_quest
            if quest_id in self.quests_db:
                new_quest = Quest.from_data(self.quests_db[quest_id])
                self.player.quest_stack.append(new_quest)
                print(f"Новый квест: {new_quest.name} - {new_quest.description}")

        self.player.add_event_record(event_type, event, chosen_choice, outcome, outcome.status_changes)


        # Обработка перехода к следующему событию
        if outcome.next_event:
            next_event_ref = outcome.next_event
            if next_event_ref.startswith("tag:"):
                tag = next_event_ref[4:]
                next_event = self.loader.get_random_event_by_tag(tag)
                if not next_event:
                    print(f"Нет событий с тегом '{tag}'. Цепочка прервана.")
                    self.player.in_event_chain = False
                    return
                print(f"\n--- Переход к случайному событию с тегом '{tag}' ---")
                self.process_event(next_event, "chain")
            else:
                next_event = self.loader.get_event_by_id(next_event_ref)
                if not next_event:
                    print(f"Событие с id '{next_event_ref}' не найдено. Цепочка прервана.")
                    self.player.in_event_chain = False
                    return
                print(f"\n--- Переход к событию '{next_event.id}' ---")
                self.process_event(next_event, "chain")
        else:
            # Цепочка завершена
            self.player.in_event_chain = False


# ------------------- Запуск -------------------

if __name__ == "__main__":
    statuses_config = load_statuses_config("statuses.yaml")
    quests_db = load_all_quests("quests")
    loader = EventLoader("events")
    game = Game(loader, statuses_config, quests_db, "characters")
    game.start()